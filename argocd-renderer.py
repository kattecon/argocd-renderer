#!/usr/bin/env python3

# ------------------------------------------------------------------------------------------
# https://github.com/kattecon/argocd-renderer
# Copyright (c) 2024 Evgeny Chukreev (https://github.com/akshaal). All Rights Reserved.
# SPDX-License-Identifier: MPL-2.0
#
# TLDR:
#   MPL-2.0 requires changes to this file to be publicly available.
#   Any modifications to this file must keep this entire header intact.
# ------------------------------------------------------------------------------------------

import argparse
import dataclasses
import os
import subprocess
import tempfile
import yaml

from dataclasses import dataclass
from typing import Type, Union


APP_NAME = "ak-argocd-renderer"


# ################################################################################################
# Utils.


def exec_capture_output(cmd_args: list[str]) -> str:
    return subprocess.check_output(cmd_args, text=True)


def resolve_repo(*, url: str, revision: str, temp_dir: str) -> None:
    global repo_resolver

    if repo_resolver:
        print("    Checking the repo path...", flush=True)
        return exec_capture_output([repo_resolver, url, revision, temp_dir]).strip()
    else:
        return ""


def parse_yaml_file(yaml_file: str) -> list[dict]:
    try:
        with open(yaml_file, "r") as file:
            return list(yaml.full_load_all(file))
    except Exception as e:
        raise ValueError(f"Failed to parse yaml file {repr(yaml_file)}") from e


def get_x(
    d: dict, name: str, err_path: str, req: bool, cls: Type, cls_name: str
) -> str:
    v = d.get(name)
    if type(v) is not cls:
        if not req and v is not None:
            raise ValueError(
                f"{err_path}.{name} must be a {cls_name}. Got: {repr(v)} in {repr(d)}"
            )
        elif req:
            raise ValueError(
                f"{err_path}.{name} is required and must be a {cls_name}. Got: {repr(v)} in {repr(d)}"
            )
    return v


def get_str(d: dict, name: str, err_path: str, req: bool) -> str:
    return get_x(d, name, err_path, req, str, "string")


def get_dict(d: dict, name: str, err_path: str, req: bool) -> dict:
    return get_x(d, name, err_path, req, dict, "dictionary")


def get_list(d: dict, name: str, err_path: str, req: bool) -> dict:
    return get_x(d, name, err_path, req, list, "list")


def get_bool(d: dict, name: str, err_path: str, req: bool) -> dict:
    return get_x(d, name, err_path, req, bool, "boolean")


def make_secure(dir: str) -> None:
    os.chmod(dir, 0o700)
    os.chown(dir, os.getuid(), os.getgid())


def dump_as_yaml_for_debug(d: dict, *, indent: str) -> None:
    return "\n".join([f"{indent}{l}" for l in yaml.dump(d).split("\n")])


# ################################################################################################
# Models.


@dataclass(frozen=True, kw_only=True)
class ResourceCtx:
    origin: str
    target_namespace: Union[str, None]
    resource: dict


@dataclass(frozen=True, kw_only=True)
class ArgocdAppSourceHelm:
    values: dict
    release_name: Union[str, None] = None
    file_parameters: list[(str, str)] = dataclasses.field(default_factory=list)
    value_files: list[str] = dataclasses.field(default_factory=list)

    @staticmethod
    def from_resource(resource: dict) -> "ArgocdAppSourceHelm":
        err_path = ".spec.source(s).helm"

        release_name = get_str(resource, "releaseName", err_path=err_path, req=False)

        values = {}
        values.update(
            get_dict(resource, "valuesObject", err_path=err_path, req=False) or {}
        )

        values_str = get_str(resource, "values", err_path=err_path, req=False)
        if values_str is not None:
            values.update(yaml.full_load(values_str))

        parameters = get_list(resource, "parameters", err_path=err_path, req=False)
        if parameters is not None:
            for parameter in parameters:
                force_string = get_bool(
                    parameter, "forceString", err_path=err_path, req=False
                )
                values[parameter["name"]] = (
                    force_string and str(parameter["value"]) or parameter["value"]
                )

        file_parameters = []
        file_parameter_err_path = err_path = err_path + ".fileParameters"
        for parameter in (
            get_list(resource, "fileParameters", err_path=err_path, req=False) or []
        ):
            file_parameters.append(
                (
                    get_str(
                        parameter,
                        "name",
                        err_path=file_parameter_err_path,
                        req=True,
                    ),
                    get_str(
                        parameter,
                        "path",
                        err_path=file_parameter_err_path,
                        req=True,
                    ),
                )
            )

        value_files = (
            get_list(resource, "valueFiles", err_path=err_path, req=False) or []
        )

        return ArgocdAppSourceHelm(
            values=values,
            release_name=release_name,
            file_parameters=file_parameters,
            value_files=value_files,
        )


@dataclass(frozen=True, kw_only=True)
class ArgocdAppSource:
    repo_url: str
    path: str
    target_revision: str
    helm: Union[ArgocdAppSourceHelm, None]
    chart: Union[str, None]
    orig_resource: dict

    @staticmethod
    def from_resource(resource: dict) -> "ArgocdAppSource":
        err_path = ".spec.source(s)"
        repo_url = get_str(resource, "repoURL", err_path=err_path, req=True)
        path = get_str(resource, "path", err_path=err_path, req=False)
        target_revision = get_str(
            resource, "targetRevision", err_path=err_path, req=True
        )

        chart = get_str(resource, "chart", err_path=err_path, req=False)
        if chart is None and path is None:
            raise ValueError(f"Either 'chart' or 'path' must be given")

        helm = get_dict(resource, "helm", err_path=err_path, req=False)
        if helm is not None:
            helm = ArgocdAppSourceHelm.from_resource(helm)

        if "kustomize" in resource:
            raise ValueError(
                f"Passing parameters via 'kustomize' dictionary is not supported"
            )

        if "directory" in resource:
            raise ValueError(f"'directory' settings are not supported")

        return ArgocdAppSource(
            repo_url=repo_url,
            path=path,
            target_revision=target_revision,
            helm=helm,
            chart=chart,
            orig_resource=resource,
        )


@dataclass(frozen=True, kw_only=True)
class ArgocdApp:
    src_file: str
    id: str
    name: str
    namespace: str
    destination_namespace: str
    sources: list[ArgocdAppSource]

    @staticmethod
    def from_resource(resource_ctx: ResourceCtx) -> "ArgocdApp":
        # Get required metadata or throw exception
        resource = resource_ctx.resource

        metadata = get_dict(resource, "metadata", err_path="", req=True)
        name = get_str(metadata, "name", err_path=".metadata", req=True)

        namespace = (
            get_str(metadata, "namespace", err_path=".metadata", req=False)
            or resource_ctx.target_namespace
        )

        if type(namespace) is not str:
            raise ValueError(
                ".metadata.namespace is required for argocd application (or it must be given as target_namespace)"
            )

        spec = get_dict(resource, "spec", err_path="", req=True)

        sources = get_list(spec, "sources", err_path=".spec", req=False)
        source = get_dict(spec, "source", err_path=".spec", req=False)

        if source is not None and sources is not None:
            raise ValueError("Only one of .spec.source or .spec.sources must be given")

        if source is not None:
            sources = [source]

        sources = [ArgocdAppSource.from_resource(source) for source in sources]

        destination = get_dict(spec, "destination", err_path=".spec", req=True)
        destination_namespace = get_str(
            destination, "namespace", err_path=".spec.destination", req=True
        )

        return ArgocdApp(
            id=f"{namespace}/{name}" or name,
            name=name,
            namespace=namespace,
            sources=sources,
            destination_namespace=destination_namespace,
            src_file=resource_ctx.origin,
        )


# ################################################################################################
# Renderer.


class ArgocdRenderer:
    def __init__(self) -> str:
        self.__pending_resources: list[ResourceCtx] = []
        self.__result_resources: list[dict] = []
        self.__processing = False
        pass

    def process_file(
        self, *, resources_file: str, target_namespace: str
    ) -> "ArgocdRenderer":
        self.__queue_resources_for_processing(
            resources=parse_yaml_file(resources_file),
            target_namespace=target_namespace,
            origin=resources_file,
        )

        if self.__processing:
            return

        self.__processing = True

        try:
            while self.__pending_resources:
                resource = self.__pending_resources.pop(0)

                try:
                    self.__process_resource(resource)
                except Exception as e:
                    resource_yaml = dump_as_yaml_for_debug(
                        resource.resource, indent="    "
                    )
                    raise ValueError(
                        f"Failed to process the following resource from {repr(resource.origin)}:\n{resource_yaml}"
                    ) from e
        finally:
            self.__processing = False

        return self

    def __queue_resources_for_processing(
        self, *, resources: list[dict], target_namespace: str, origin: str
    ) -> "ArgocdRenderer":
        for resource in resources:
            self.__pending_resources.append(
                ResourceCtx(
                    target_namespace=target_namespace,
                    resource=resource,
                    origin=origin,
                )
            )

        return self

    def __queue_all_resource_files_in_dir_rec(
        self, *, base_dir: str, dir_origin: str, target_namespace: str
    ) -> None:
        walk = list(os.walk(base_dir))
        walk.sort(key=lambda x: x[0])

        for file_dir, _, files in walk:
            files = list(files)
            files.sort()

            for file in files:
                file_path = os.path.join(file_dir, file)

                parsed_output = parse_yaml_file(file_path)
                base_rel_file_path = os.path.relpath(file_path, base_dir)

                print(
                    f"    ... found {len(parsed_output)} resources in {repr(base_rel_file_path)}."
                )
                self.__queue_resources_for_processing(
                    resources=parsed_output,
                    target_namespace=target_namespace,
                    origin=dir_origin + " / " + base_rel_file_path,
                )

    def __process_resource(self, resource_ctx: ResourceCtx) -> None:
        resource = resource_ctx.resource
        if type(resource) is not dict:
            raise ValueError(
                f"The resource must be a dictionary, but got '{repr(resource)}'"
            )

        api_version = get_str(resource, "apiVersion", err_path="", req=False)
        kind = get_str(resource, "kind", err_path="", req=False)

        self.__result_resources.append(resource)

        if api_version == "argoproj.io/v1alpha1" and kind == "Application":
            self.__process_argocd_application(resource_ctx)

    def __process_argocd_application(self, resource_ctx: ResourceCtx) -> None:
        app = ArgocdApp.from_resource(resource_ctx)

        print(
            f"Processing argocd application {repr(app.id)} from {repr(resource_ctx.origin)}..."
        )

        for source in app.sources:
            print(
                f"  Source:  {repr(source.repo_url)} @ {repr(source.target_revision)}  /  {repr(source.path or source.chart)}"
            )

            with tempfile.TemporaryDirectory(prefix=APP_NAME) as temp_dir:
                make_secure(temp_dir)

                try:
                    self.__process_argocd_application_source(
                        resource_ctx, app, source, temp_dir
                    )
                except Exception as e:
                    resource_yaml = dump_as_yaml_for_debug(
                        source.orig_resource, indent="    "
                    )
                    raise ValueError(
                        f"Failed to process argocd application source:\n{resource_yaml}"
                    ) from e

            print("")

    def __process_argocd_application_source(
        self,
        resource_ctx: ResourceCtx,
        app: ArgocdApp,
        source: ArgocdAppSource,
        temp_dir: str,
    ) -> None:
        if source.chart is None:
            resolved_repo_path = resolve_repo(
                url=source.repo_url,
                revision=source.target_revision,
                temp_dir=temp_dir,
            )
            if resolved_repo_path == "":
                raise ValueError(f"Failed to resolve the repository path...")
        else:
            resolved_repo_path = ""

        if source.helm is not None or source.chart is not None:
            kind = "helm"
        else:
            kind = None
            if resolved_repo_path != "":
                src_dir = resolved_repo_path + "/" + source.path
                if os.path.exists(os.path.join(src_dir, "Chart.yaml")):
                    kind = "helm"
                elif os.path.exists(os.path.join(src_dir, "kustomization.yaml")):
                    kind = "kustomize"
                else:
                    kind = "simple"

        if kind == "helm":
            if source.helm is None:
                # Looks like the app is referring a helm chart without using values in the app definition.
                source = dataclasses.replace(
                    source, helm=ArgocdAppSourceHelm(values={})
                )

            handler = self.__process_argocd_application_helm_source
        elif kind == "kustomize":
            handler = self.__process_argocd_application_kustomize_source
        elif kind == "simple":
            handler = self.__process_argocd_application_simple_source
        else:
            raise ValueError(
                f"Unknown/unsupported source type in argocd application {repr(app.id)} in {repr(resource_ctx.origin)}"
            )

        handler(resource_ctx, app, source, temp_dir, resolved_repo_path)

    def __process_argocd_application_simple_source(
        self,
        resource_ctx: ResourceCtx,
        app: ArgocdApp,
        source: ArgocdAppSource,
        _temp_dir: str,
        resolved_repo_path,
    ) -> None:
        print("    Using resource from the directory as-is...", flush=True)
        self.__queue_all_resource_files_in_dir_rec(
            base_dir=resolved_repo_path + "/" + source.path,
            dir_origin=resource_ctx.origin + " / " + app.id,
            target_namespace=app.destination_namespace,
        )

        print("    Done.")
        print("")

    def __process_argocd_application_kustomize_source(
        self,
        resource_ctx: ResourceCtx,
        app: ArgocdApp,
        source: ArgocdAppSource,
        _temp_dir: str,
        resolved_repo_path,
    ) -> None:
        print("    Preparing to process with kubectl kustomize...", flush=True)

        kustomize_args = ["kubectl", "kustomize"]
        kustomize_args += additional_kustomize_args or []
        kustomize_args.append(resolved_repo_path + "/" + source.path)

        print("    Rendering using kubectl kustomize...", flush=True)
        output = exec_capture_output(kustomize_args)

        self.__queue_resources_for_processing(
            resources=yaml.full_load_all(output),
            target_namespace=app.destination_namespace,
            origin=resource_ctx.origin + " / " + app.id,
        )

        print("    Done.")
        print("")

    def __process_argocd_application_helm_source(
        self,
        resource_ctx: ResourceCtx,
        app: ArgocdApp,
        source: ArgocdAppSource,
        temp_dir: str,
        resolved_repo_path,
    ) -> None:
        print("    Preparing to process with helm...", flush=True)

        # Write values file.
        values_file = os.path.join(temp_dir, "values.yaml")
        with open(values_file, "w") as file:
            yaml.dump(source.helm.values, file)

        # Create directory for helm output.
        output_dir = os.path.join(temp_dir, "output")
        os.mkdir(output_dir)

        # Run 'helm template'.
        helm_args = ["helm", "template", "--dry-run", "--dependency-update"]

        if source.chart != "":
            helm_args += ["--repo", source.repo_url]

        for value_file in source.helm.value_files:
            helm_args += ["--values", value_file]

        helm_args += [
            "--version",
            source.target_revision,
            "--namespace",
            app.destination_namespace,
            "--values",
            values_file,
            "--output-dir",
            output_dir,
        ]

        helm_args += additional_helm_args or []

        for name, path in source.helm.file_parameters:
            helm_args += ["--set-file", f"{name}={path}"]

        orig_cwd = os.getcwd()

        print("    Running helm...", flush=True)
        try:
            helm_args.append(source.helm.release_name or app.name)

            if source.chart:
                helm_args.append(source.chart)
            else:
                chart_path = resolved_repo_path + "/" + source.path
                helm_args.append(chart_path)
                os.chdir(chart_path)

            exec_capture_output(helm_args)
        finally:
            os.chdir(orig_cwd)

        self.__queue_all_resource_files_in_dir_rec(
            base_dir=output_dir,
            dir_origin=resource_ctx.origin + " / " + app.id,
            target_namespace=app.destination_namespace,
        )

        print("    Done.")
        print("")

    def write_result(self, output_file: str) -> None:
        print(f"Writing result to {repr(output_file)}...")

        try:
            with open(output_file, "w") as file:
                yaml.dump_all(self.__result_resources, file)
        except Exception as e:
            raise ValueError(f"Failed to write result to {repr(output_file)}") from e

        print("")


# ################################################################################################
# Main / CLI.


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Render argocd application manifests from the given resources yaml file."
    )

    parser.add_argument(
        "-o",
        "--output",
        dest="output_file",
        metavar="output_yaml_file",
        type=str,
        help="output file to save the resources rendered for the found argocd application manifests",
        required=True,
    )

    parser.add_argument(
        "-n",
        "--namespace",
        dest="target_namespace",
        metavar="target_namespace",
        type=str,
        help="target namespace to be used in the argocd application manifest if not explicitly given in the resources file",
    )

    parser.add_argument(
        "-r",
        "--repo-resolver",
        dest="repo_resolver",
        metavar="repo_resolver",
        type=str,
        help="path to the repository resolver script that takes [repo url, revision, temp_dir] and returns the resolved local path or empty string",
    )

    parser.add_argument(
        "-a",
        "--helm-args",
        dest="helm_args",
        metavar="helm_args",
        type=str,
        help="json/yaml array of strings to pass as additional arguments to helm command",
    )

    parser.add_argument(
        "-k",
        "--kustomize-args",
        dest="kustomize_args",
        metavar="kustomize_args",
        type=str,
        help="json/yaml array of strings to pass as additional arguments to kustomize command",
    )

    parser.add_argument(
        "resources_file",
        metavar="resources_yaml_file",
        type=str,
        help="resources file containing the resources to be used in the argocd application manifest",
    )

    args = parser.parse_args()

    global repo_resolver
    repo_resolver = args.repo_resolver

    global additional_helm_args
    if args.helm_args:
        try:
            additional_helm_args = yaml.full_load(args.helm_args)
        except Exception as e:
            raise ValueError(
                f"Failed to parse additional helm arguments: {repr(args.helm_args)}"
            ) from e
    else:
        additional_helm_args = []

    global additional_kustomize_args
    if args.kustomize_args:
        try:
            additional_kustomize_args = yaml.full_load(args.kustomize_args)
        except Exception as e:
            raise ValueError(
                f"Failed to parse additional kustomize arguments: {repr(args.kustomize_args)}"
            ) from e
    else:
        additional_kustomize_args = []

    try:
        ArgocdRenderer().process_file(
            resources_file=args.resources_file, target_namespace=args.target_namespace
        ).write_result(args.output_file)
    except Exception as e:
        # Flush stdout
        print("", flush=True)
        print(
            "--- terminated script because of unexpected error (see also above for a possible reason) ---",
            flush=True,
        )
        raise e
