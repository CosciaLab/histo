process WRITE_FEATURES {
    label "process_low"
    tag "${meta.sample}"

    conda "${moduleDir}/environment.yml"
    container "docker.io/josenimo/sopa:2.3.0"

    input:
    // Writes into the store after WRITE_SEGMENTATIONS; never in parallel with it (they race on its metadata).
    tuple val(meta), path(sdata_path), path(tables)

    output:
    tuple val(meta), path(sdata_path)
    path "versions.yml"

    script:
    """
    write_features.py \\
        --sdata ${sdata_path} \\
        --tables ${tables}

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        sopa: \$(sopa --version)
    END_VERSIONS
    """

    stub:
    // Lists what was staged and from where, as WRITE_SEGMENTATIONS' stub does.
    """
    for f in ${tables}; do echo "\$f \$(readlink \$f)"; done > staged_inputs.txt

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        sopa: stub
    END_VERSIONS
    """
}
