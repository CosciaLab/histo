process RESOLVE {
    label "process_single"
    tag "${meta.sample}:${spec.name}"

    conda "${moduleDir}/environment.yml"
    container "docker.io/josenimo/sopa:2.2.12"

    input:
    // sdata_path is only read; parquets are one spec's patches, staged as 0.parquet, 1.parquet, ...
    tuple val(meta), path(sdata_path), val(spec), path(parquets)

    output:
    // Named after the spec: WRITE_SEGMENTATIONS takes the element name from the file stem.
    tuple val(meta), val(spec), path("${spec.name}.parquet")
    path "versions.yml"

    script:
    def spec_json = groovy.json.JsonOutput.toJson(spec)
    """
    cat <<'END_SPEC' > spec.json
    ${spec_json}
    END_SPEC

    resolve_segmentation.py \\
        --sdata ${sdata_path} \\
        --spec spec.json \\
        --patches ${parquets} \\
        --output ${spec.name}.parquet

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        sopa: \$(sopa --version)
    END_VERSIONS
    """

    stub:
    """
    touch ${spec.name}.parquet

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        sopa: stub
    END_VERSIONS
    """
}
