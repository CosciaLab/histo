process ASHLAR {
    tag "$meta.id"
    label 'process_single'

    // PATCH: josenimo/ashlar fork (rotation correction, -c -1, --qc-output); see docs/decisions.md.
    conda "${moduleDir}/environment.yml"
    container "docker.io/josenimo/jose_ashlar:1.22.0-jose.1"

    input:
    tuple val(meta), path(images, stageAs: 'image*/*')
    path(opt_dfp, stageAs: 'dfp*/*')
    path(opt_ffp, stageAs: 'ffp*/*')

    output:
    tuple val(meta), path("*.ome.tif"), emit: tif
    tuple val(meta), path("*_ashlar_qc"), emit: qc, optional: true
    tuple val("${task.process}"), val('ashlar'), eval(workflow.stubRun ? 'echo stub' : "ashlar --version | sed 's/^.*ashlar //'"), emit: versions_ashlar, topic: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def args          = task.ext.args           ?: ''
    def prefix        = task.ext.prefix         ?: "${meta.id}"
    def dfp           = opt_dfp                 ? "--dfp ${opt_dfp}" : ""
    def ffp           = opt_ffp                 ? "--ffp ${opt_ffp}" : ""
    def num_files     = images instanceof List  ? images.size()      : 1
    def opt_dfp_size  = opt_dfp instanceof List ? opt_dfp.size()     : 1
    def opt_ffp_size  = opt_ffp instanceof List ? opt_ffp.size()     : 1
    def dfp_validated = (opt_dfp_size == 0 || opt_dfp_size == 1 || opt_dfp_size == num_files) ? true : false
    def ffp_validated = (opt_ffp_size == 0 || opt_ffp_size == 1 || opt_ffp_size == num_files) ? true : false

    if ( !dfp_validated ) { error "Please input only zero, one, or N dfp files, where N is the number of input images" }
    if ( !ffp_validated ) { error "Please input only zero, one, or N ffp files, where N is the number of input images" }

    // PATCH: QC is written before the mosaic, so a failed write still leaves it in the work dir.
    def qc_dir  = "${prefix}_ashlar_qc"
    def qc_args = task.ext.qc ? "--qc-output ${qc_dir} --report ${qc_dir}/${prefix}_ashlar_report.pdf" : ""
    def tee_log = task.ext.qc ? "2>&1 | tee ${qc_dir}/ashlar.log" : ""

    """
    export JAVA_TOOL_OPTIONS='-XX:+PerfDisableSharedMem'
    export XDG_CACHE_HOME=.cache
    export MPLCONFIGDIR=.matplotlib
    ${task.ext.qc ? "mkdir -p ${qc_dir}" : ""}

    ashlar \\
        -o ${prefix}.ome.tif \\
        ${images} \\
        ${args} \\
        ${qc_args} \\
        ${dfp} \\
        ${ffp} ${tee_log}

    sed -i -E 's/UUID="urn:uuid:[[:xdigit:]]{8}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{12}"/                                                    /g' ${prefix}.ome.tif
    """

    stub:
    def prefix        = task.ext.prefix         ?: "${meta.id}"
    def num_files     = images instanceof List  ? images.size()  : 1
    def opt_dfp_size  = opt_dfp instanceof List ? opt_dfp.size() : 1
    def opt_ffp_size  = opt_ffp instanceof List ? opt_ffp.size() : 1
    def dfp_validated = (opt_dfp_size == 0 || opt_dfp_size == 1 || opt_dfp_size == num_files) ? true : false
    def ffp_validated = (opt_ffp_size == 0 || opt_ffp_size == 1 || opt_ffp_size == num_files) ? true : false

    if ( !dfp_validated ) { error "Please input only zero, one, or N dfp files, where N is the number of input images" }
    if ( !ffp_validated ) { error "Please input only zero, one, or N ffp files, where N is the number of input images" }

    def qc_dir        = "${prefix}_ashlar_qc"
    """
    export JAVA_TOOL_OPTIONS='-XX:+PerfDisableSharedMem'

    touch ${prefix}.ome.tif
    ${task.ext.qc ? "mkdir -p ${qc_dir} && echo '{\"schema_version\": 1, \"stub\": true}' > ${qc_dir}/qc.json && touch ${qc_dir}/tiles.csv ${qc_dir}/edges.csv ${qc_dir}/ashlar.log" : ""}
    """
}
