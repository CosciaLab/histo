process AGGREGATE {
    label "process_medium"
    tag "${meta.sample}:${method}"

    conda "${moduleDir}/environment.yml"
    container "docker.io/josenimo/sopa:2.3.0"

    input:
    // sdata_path is only read; specs are this method's spec maps. shapes: {method}_cells.parquet,
    // plus LINK_COMPARTMENTS' parquets when both targets ran; {method}_nuclei.parquet in a nuclei-only run.
    tuple val(meta), path(sdata_path), val(method), val(specs), path(shapes)

    output:
    tuple val(meta), val(method), path("${method}_table.h5ad")
    path "versions.yml"

    script:
    def args = task.ext.args ?: ""
    def specs_json = groovy.json.JsonOutput.toJson(specs)
    // meta.slide is set only on dearrayed TMAs, where meta.id is the core.
    def core_id_arg = meta.slide ? "--core-id ${meta.id}" : ""
    // Rows are cells when cells were segmented, else nuclei; with both, the linked compartments are layers.
    def targets = specs*.target
    def target = 'cells' in targets ? 'cells' : 'nuclei'
    def compartment_args = targets.containsAll(['cells', 'nuclei'])
        ? "--nuclei-compartment ${method}_nucleus_compartment.parquet --cytoplasm ${method}_cytoplasm.parquet --links ${method}_links.parquet"
        : ""
    """
    cat <<'END_SPECS' > specs.json
    ${specs_json}
    END_SPECS

    aggregate_compartments.py \\
        --sdata ${sdata_path} \\
        --method ${method} \\
        --shapes ${method}_${target}.parquet \\
        --target ${target} \\
        ${compartment_args} \\
        --specs specs.json \\
        --slide ${meta.slide ?: meta.sample} \\
        ${core_id_arg} \\
        ${args} \\
        --output ${method}_table.h5ad

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        sopa: \$(sopa --version)
    END_VERSIONS
    """

    stub:
    """
    touch ${method}_table.h5ad

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        sopa: stub
    END_VERSIONS
    """
}
