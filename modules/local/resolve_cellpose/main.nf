process RESOLVE_CELLPOSE {
    label "process_low"
    tag "${meta.sample}"

    conda "${moduleDir}/environment.yml"
    container "docker.io/josenimo/sopa:2.2.12"

    input:
    tuple val(meta), path(sdata_path), path(parquets)

    output:
    tuple val(meta), path(sdata_path)
    path "versions.yml"

    script:
    """
    mkdir -p ${sdata_path}/.sopa_cache/cellpose_boundaries
    for f in ${parquets}; do
        mv "\$f" "${sdata_path}/.sopa_cache/cellpose_boundaries/"
    done

    sopa resolve cellpose ${sdata_path}

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        sopa: \$(sopa --version)
        cellpose: \$(python -c "import importlib.metadata as m; print(m.version('cellpose'))")
    END_VERSIONS
    """

    stub:
    """
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        sopa: stub
        cellpose: stub
    END_VERSIONS
    """
}
