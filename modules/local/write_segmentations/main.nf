process WRITE_SEGMENTATIONS {
    label "process_single"
    tag "${meta.sample}"

    conda "${moduleDir}/environment.yml"
    container "docker.io/josenimo/sopa:2.2.12"

    input:
    // The only task that writes shapes and tables into the store (parallel writers race on its metadata).
    tuple val(meta), path(sdata_path), path(shapes), path(tables)

    output:
    tuple val(meta), path(sdata_path)
    path "versions.yml"

    script:
    def args = task.ext.args ?: ''
    """
    write_segmentations.py \\
        --sdata ${sdata_path} \\
        --shapes ${shapes} \\
        --tables ${tables} \\
        ${args}

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        sopa: \$(sopa --version)
    END_VERSIONS
    """

    stub:
    """
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        sopa: stub
    END_VERSIONS
    """
}
