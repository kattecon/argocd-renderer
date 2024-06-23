# argocd-renderer

This is a simple Python script for rendering ArgoCD application manifests
the same way ArgoCD would do it.

The script processes a given resource YAML file as input and writes the results to
an output file. It accomplishes this by copying all the original resources
to the output, and additionally, for any ArgoCD applications it encounters,
it renders the application manifest and includes all the rendered resources
in the output file as well. The process is recursive: all the rendered
resources are also processed as if they were input.

## Goals

- Render ArgoCD applications as close as possible to how ArgoCD would do it.
- Keep the script simple and easy to understand. One file, no special dependencies.

## Compatibility

There is no plan to implement all the rendering options available in ArgoCD.
ArgoCD is a complex system with many features some of which require a running
Kubernetes cluster. Additionally, certain features would significantly
complicate the code.

The following options are supported:

- [.spec.source.helm.valuesObject](./tests/test-01/input.yaml)
- [.spec.source.helm.releaseName](./tests/test-04/input.yaml)
- [.spec.source.helm.parameters](./tests/test-04/input.yaml)
- [.spec.source.helm.fileParameters](./tests/test-04/input.yaml)
- [.spec.source.helm.values](./tests/test-04/input.yaml)
- [.spec.source.helm.valueFiles](./tests/test-04/input.yaml)
- [.spec.source.chart](./tests/test-06/input.yaml)
- [kustomization.yaml](./tests/test-20/input.yaml)
- [directory source](./tests/test-40/input.yaml)

The following features are not supported:

- [.spec.source.kustomize](https://argo-cd.readthedocs.io/en/stable/user-guide/kustomize/#patches)
  is not supported. Use `kustomization.yaml` file instead.
- [.spec.source.directory](https://argo-cd.readthedocs.io/en/stable/user-guide/directory/)
  options are not supported. Note, this means that the only the configuration
  options are not supported. The directory source itself is supported.
- [ApplicationSet](https://argo-cd.readthedocs.io/en/stable/user-guide/application-set/)
  is not supported.

## Repository access

The script doesn't have an ability to download repositories. Instead, there is
an option to call a helper script that can resolve a repository URL to a local
path. The helper script is called with the following arguments:

- `repo_url`: the URL of the repository to resolve.
- `revision`: the revision to checkout.
- `temp_dir`: a temporary directory that can be used to store the repository
              (as a subdirectory in it).

The helper script can either return the resolved path or an empty string if
the repository can't be resolved. The implementation of the helper script
can either checkout the repository or use a local cache or return a path to
an already checked out repository.

See the [repo-resolver.sh](./tests/repo-resolver.sh) script for an example.

## Installation and requirements

- Python 3 is required.
- kubectl is required for kustomize to work.
- Helm is required to render Helm charts.

Installation is not required. Just download [the script](./argocd-renderer.py)
and enjoy.

## Command line arguments

```text
usage: argocd-renderer.py
           [-h] -o output_yaml_file [-n target_namespace]
           [-r repo_resolver] [-a helm_args] [-k kustomize_args]
           resources_yaml_file

  resources_yaml_file   resources file containing the resources to be used in
                        the argocd application manifest.

options:
  -o output_yaml_file, --output output_yaml_file
                        output file to save the resources rendered for
                        the found argocd application manifests.

  -n target_namespace, --namespace target_namespace
                        target namespace to be used in the argocd application
                        manifest if not explicitly given in the resources file.

  -r repo_resolver, --repo-resolver repo_resolver
                        path to the repository resolver script that takes
                        [repo url, revision, temp_dir] and returns the resolved
                        local path or empty string.

  -a helm_args, --helm-args helm_args
                        json/yaml array of strings to pass as additional
                        arguments to helm command.

  -k kustomize_args, --kustomize-args kustomize_args
                        json/yaml array of strings to pass as additional
                        arguments to kustomize command.
```
