process LINK_COMPARTMENTS {
    label "process_low"
    tag "${meta.sample}:${method}"

    conda "${moduleDir}/environment.yml"
    container "docker.io/josenimo/sopa:2.2.12"

    input:
    // one method's resolved cells and nuclei from RESOLVE
    tuple val(meta), val(method), path(cells), path(nuclei)

    output:
    // In linked/: {method}_nuclei.parquet is also the input's name, and an output must not overwrite its staged input.
    tuple val(meta), val(method), path("linked/*.parquet")
    path "versions.yml"

    script:
    """
    link_compartments.py \\
        --cells ${cells} \\
        --nuclei ${nuclei} \\
        --method ${method} \\
        --out-dir linked

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        geopandas: \$(python -c "import geopandas; print(geopandas.__version__)")
        shapely: \$(python -c "import shapely; print(shapely.__version__)")
    END_VERSIONS
    """

    stub:
    """
    mkdir linked
    touch linked/${method}_nuclei.parquet
    touch linked/${method}_cytoplasm.parquet
    touch linked/${method}_nucleus_compartment.parquet
    touch linked/${method}_links.parquet

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        geopandas: stub
        shapely: stub
    END_VERSIONS
    """
}
