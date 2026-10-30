process PATCH_SEGMENTATION_CELLPOSE {
    label "process_single"
    tag "${meta.sample}"

    conda "${moduleDir}/environment.yml"
    // cpsam weights are baked into the image (CELLPOSE_LOCAL_MODELS_PATH=/opt/cellpose_models).
    container "docker.io/josenimo/sopa:2.2.12"

    input:
    tuple val(meta), path(sdata_path), val(cli_arguments), val(index), val(n_patches)

    output:
    tuple val(meta), path(sdata_path), path("${index}.parquet"), val(n_patches)
    path "versions.yml"

    script:
    // use_gpu: fail here rather than let the backend fall back to CPU without a word.
    def gpu_check = task.accelerator ? """python -c "import torch; torch.ones(1, device='cuda').sum().item()" || { echo 'use_gpu: CUDA is not usable in this task' >&2; exit 1; }""" : ""
    def gpu = task.accelerator ? "--gpu" : "--no-gpu"
    """
    ${gpu_check}
    sopa segmentation cellpose ${sdata_path} --patch-index ${index} ${cli_arguments} ${gpu}

    mv ${sdata_path}/.sopa_cache/cellpose_boundaries/${index}.parquet ${index}.parquet

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        sopa: \$(sopa --version)
        cellpose: \$(python -c "import importlib.metadata as m; print(m.version('cellpose'))")
    END_VERSIONS
    """

    stub:
    """
    touch ${index}.parquet

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        sopa: stub
        cellpose: stub
    END_VERSIONS
    """
}
