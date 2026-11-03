// Choose one downsample factor per slide from COREOGRAPH_DETECT's metrics.
process COREOGRAPH_SELECT {
    tag "${meta.id}"
    label 'process_single'

    container "docker.io/labsyspharm/unetcoreograph:2.4.6"

    input:
    tuple val(meta), path(metrics), path(overlays)

    output:
    tuple val(meta), path("*_selection.json")                         , emit: selection
    tuple val(meta), path("*_sweep.tsv"), path("*_sweep_overlays.png"), emit: report
    tuple val("${task.process}"), val('coreograph'), val("2.4.6"), topic: versions, emit: versions_coreograph

    when:
    task.ext.when == null || task.ext.when

    script:
    def prefix = task.ext.prefix ?: "${meta.id}"
    """
    export MPLCONFIGDIR=\$PWD

    coreograph_select.py \\
        --metrics ${metrics} \\
        --overlays ${overlays} \\
        --prefix ${prefix}
    """

    stub:
    def prefix = task.ext.prefix ?: "${meta.id}"
    """
    echo '{"downsample_factor": 5, "warning": null}' > ${prefix}_selection.json
    touch ${prefix}_sweep.tsv
    touch ${prefix}_sweep_overlays.png
    """
}
