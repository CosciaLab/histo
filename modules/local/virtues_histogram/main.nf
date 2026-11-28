process VIRTUES_HISTOGRAM {
    label "process_low"
    tag "${meta.sample}:virtues_histogram"

    conda "${moduleDir}/environment.yml"
    // virtues_stats.py imports no torch, so the sopa image is enough.
    container "docker.io/josenimo/sopa:2.3.0-1"

    input:
    // sdata_path is only read; spec.channels is a list of [name, uniprot_id] pairs, resolved upstream.
    tuple val(meta), path(sdata_path), val(spec)

    output:
    tuple val(meta), path("${meta.sample}_virtues_hist.npz")
    path "versions.yml"

    script:
    def channels = spec.channels.collect { "${it[0]}:${it[1]}" }.join(',')
    """
    virtues_stats.py histogram \\
        --sdata ${sdata_path} \\
        --channels '${channels}' \\
        --pixel-size ${spec.pixel_size} \\
        --output ${meta.sample}_virtues_hist.npz

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        sopa: \$(sopa --version)
    END_VERSIONS
    """

    stub:
    """
    echo "${task.accelerator ? 'gpu' : 'none'}" > .accelerator
    touch ${meta.sample}_virtues_hist.npz

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        sopa: stub
    END_VERSIONS
    """
}
