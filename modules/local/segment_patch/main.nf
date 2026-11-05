process SEGMENT_PATCH {
    label "process_single"
    tag "${meta.sample}:${spec.name}:${index}"

    conda "${moduleDir}/environment.yml"
    // Weights are baked into the image: no download at run time, and the cluster may be offline.
    container "docker.io/josenimo/sopa:2.3.0"

    input:
    // sdata_path is only read; spec is a map from segmentationSpecs (modules/local/utils.nf).
    tuple val(meta), path(sdata_path), val(spec), val(index), val(n_patches)

    output:
    tuple val(meta), val(spec), path("${index}.parquet"), val(n_patches)
    path "versions.yml"

    script:
    // use_gpu: fail here rather than let the backend fall back to CPU without a word.
    def gpu_check = task.accelerator ? """python -c "import torch; torch.ones(1, device='cuda').sum().item()" || { echo 'use_gpu: CUDA is not usable in this task' >&2; exit 1; }""" : ""
    // A flag, not a spec field: task.accelerator is the only source, so config and tool cannot disagree.
    def device = task.accelerator ? "cuda" : "cpu"
    def spec_json = groovy.json.JsonOutput.toJson(spec)
    """
    ${gpu_check}
    cat <<'END_SPEC' > spec.json
    ${spec_json}
    END_SPEC

    segment_patch.py \\
        --sdata ${sdata_path} \\
        --spec spec.json \\
        --patch-index ${index} \\
        --device ${device} \\
        --output ${index}.parquet

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        sopa: \$(sopa --version)
        cellpose: \$(python -c "import importlib.metadata as m; print(m.version('cellpose'))")
        instanseg: \$(python -c "import importlib.metadata as m; print(m.version('instanseg-torch'))")
    END_VERSIONS
    """

    stub:
    """
    touch ${index}.parquet

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        sopa: stub
        cellpose: stub
        instanseg: stub
    END_VERSIONS
    """
}
