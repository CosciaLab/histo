process WRITE_FEATURES {
    label "process_low"
    tag "${meta.sample}"

    conda "${moduleDir}/environment.yml"
    container "docker.io/josenimo/sopa:2.3.0-1"

    input:
    // Writes into the store after WRITE_SEGMENTATIONS; never in parallel with it (they race on its metadata).
    tuple val(meta), path(sdata_path), path(features)

    output:
    tuple val(meta), path(sdata_path)
    path "versions.yml"

    script:
    // Split by suffix; --shapes is left out when no niche was kept.
    def files  = features instanceof List ? features : [features]
    def tables = files.findAll { it.name.endsWith('.h5ad') }.join(' ')
    def shapes = files.findAll { it.name.endsWith('.parquet') }.join(' ')
    """
    write_features.py \\
        --sdata ${sdata_path} \\
        --tables ${tables}${shapes ? " \\\n        --shapes ${shapes}" : ''}

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        sopa: \$(sopa --version)
    END_VERSIONS
    """

    stub:
    // Lists what was staged and from where, as WRITE_SEGMENTATIONS' stub does.
    """
    for f in ${features instanceof List ? features.join(' ') : features}; do echo "\$f \$(readlink \$f)"; done > staged_inputs.txt

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        sopa: stub
    END_VERSIONS
    """
}
