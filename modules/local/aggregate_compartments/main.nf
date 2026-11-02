process AGGREGATE_COMPARTMENTS {
    label "process_medium"
    tag "${meta.sample}:${method}"

    conda "${moduleDir}/environment.yml"
    container "docker.io/josenimo/sopa:2.2.12"

    input:
    // sdata_path is only read; specs are this method's spec maps, shapes its resolved parquets
    tuple val(meta), path(sdata_path), val(method), val(specs), path(shapes)

    output:
    tuple val(meta), val(method), path("${method}_table.h5ad")
    path "versions.yml"

    script:
    def args = task.ext.args ?: ""
    def specs_json = groovy.json.JsonOutput.toJson(specs)
    // meta.slide is set only on dearrayed TMAs, where meta.id is the core.
    def core_id_arg = meta.slide ? "--core-id ${meta.id}" : ""
    """
    cat <<'END_SPECS' > specs.json
    ${specs_json}
    END_SPECS

    aggregate_compartments.py \\
        --sdata ${sdata_path} \\
        --method ${method} \\
        --cells ${method}_cells.parquet \\
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
