// Detect TMA cores at one downsample factor k, without writing core tiles.
// Same image as COREOGRAPH: the script imports UNetCoreograph from /app.
process COREOGRAPH_DETECT {
    tag "${meta.id} k=${k}"
    label 'process_single'

    container "docker.io/labsyspharm/unetcoreograph:2.4.6"

    input:
    tuple val(meta), path(image), val(k)

    output:
    tuple val(meta), path("*_k*_metrics.json"), path("*_k*_overlay.png")  , emit: results
    tuple val(meta), path("*_k*_coremask.tif"), path("*_k*_centroids.txt"), emit: labels
    tuple val("${task.process}"), val('coreograph'), val("2.4.6"), topic: versions, emit: versions_coreograph

    when:
    task.ext.when == null || task.ext.when

    script:
    def args   = task.ext.args ?: ''
    def prefix = task.ext.prefix ?: "${meta.id}"
    """
    export MPLCONFIGDIR=\$PWD

    coreograph_detect.py \\
        --image ${image} \\
        --downsample-factor ${k} \\
        --prefix ${prefix} \\
        ${args}
    """

    stub:
    def prefix = task.ext.prefix ?: "${meta.id}"
    """
    echo '{"k": ${k}, "n_cores": 2}' > ${prefix}_k${k}_metrics.json
    touch ${prefix}_k${k}_overlay.png
    touch ${prefix}_k${k}_coremask.tif
    touch ${prefix}_k${k}_centroids.txt
    """
}
