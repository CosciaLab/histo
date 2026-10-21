process PUBLISH_SPATIALDATA {
    label "process_single"
    tag "${meta.sample}"

    publishDir "${params.outdir}", mode: params.publish_dir_mode

    input:
    tuple val(meta), path(sdata_path)

    output:
    tuple val(meta), path(sdata_path), emit: sdata

    script:
    // Empty publish sink, so the store is published once, after the last step that writes to it.
    // No tool, so no versions (see .lint-allow-no-versions).
    """
    true
    """

    stub:
    """
    true
    """
}
