process NIMBUS {
    label "process_medium"
    label "process_long"
    tag "${meta.sample}:${method}:nimbus"

    conda "${moduleDir}/environment.yml"
    // Weights are baked into the image: no download at run time, and the cluster may be offline.
    container "docker.io/josenimo/nimbus:0.0.5"

    input:
    // sdata_path is only read; spec is a map from featureSpecs (modules/local/utils.nf).
    tuple val(meta), path(sdata_path), val(method), val(spec)

    output:
    tuple val(meta), val(method), val(spec), path("${method}_nimbus.h5ad"), path("${method}_nimbus.json")
    path "versions.yml"

    script:
    // use_gpu: fail here rather than let the backend fall back to CPU without a word.
    def gpu_check = task.accelerator ? """python -c "import torch; torch.ones(1, device='cuda').sum().item()" || { echo 'use_gpu: CUDA is not usable in this task' >&2; exit 1; }""" : ""
    // A flag, not a spec field: task.accelerator is the only source, so config and tool cannot disagree.
    def device = task.accelerator ? "cuda" : "cpu"
    """
    ${gpu_check}
    nimbus_cells.py \\
        --sdata ${sdata_path} \\
        --method ${method} \\
        --channels '${spec.channels.join(',')}' \\
        --pixel-size ${spec.pixel_size} \\
        --device ${device} \\
        --output ${method}_nimbus.h5ad \\
        --provenance ${method}_nimbus.json

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        nimbus-inference: \$(python -c "import importlib.metadata as m; print(m.version('nimbus-inference'))")
        torch: \$(python -c "import torch; print(torch.__version__)")
    END_VERSIONS
    """

    stub:
    """
    touch ${method}_nimbus.h5ad ${method}_nimbus.json

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        nimbus-inference: stub
        torch: stub
    END_VERSIONS
    """
}
