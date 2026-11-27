process VIRTUES_STATS {
    label "process_single"
    tag "${slide}:virtues_stats"

    conda "${moduleDir}/environment.yml"
    // virtues_stats.py imports no torch, so the sopa image is enough.
    container "docker.io/josenimo/sopa:2.3.0-1"

    input:
    // hists are the per-core histograms of one slide; the statistics are slide-wide.
    tuple val(slide), path(hists), val(spec)

    output:
    tuple val(slide), path("${slide}_virtues_stats.json")
    path "versions.yml"

    script:
    """
    virtues_stats.py combine \\
        --slide ${slide} \\
        --pixel-size ${spec.pixel_size} \\
        --output ${slide}_virtues_stats.json \\
        ${hists}

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        sopa: \$(sopa --version)
    END_VERSIONS
    """

    stub:
    """
    echo "${task.accelerator ? 'gpu' : 'none'}" > .accelerator
    touch ${slide}_virtues_stats.json

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        sopa: stub
    END_VERSIONS
    """
}
