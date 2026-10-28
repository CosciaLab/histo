process RESOLVE_INSTANSEG {
    label "process_low"
    tag "${meta.sample}"

    conda "${moduleDir}/environment.yml"
    container "docker.io/josenimo/sopa-seg:2.2.12"

    input:
    tuple val(meta), path(sdata_path), path(parquets)

    output:
    tuple val(meta), path(sdata_path)
    path "versions.yml"

    script:
    """
    mkdir -p ${sdata_path}/.sopa_cache/instanseg_boundaries
    for f in ${parquets}; do
        mv "\$f" "${sdata_path}/.sopa_cache/instanseg_boundaries/"
    done

    sopa resolve instanseg ${sdata_path}

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        sopa: \$(sopa --version)
        instanseg: \$(python -c "import importlib.metadata as m; print(m.version('instanseg-torch'))")
    END_VERSIONS
    """

    stub:
    """
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        sopa: stub
        instanseg: stub
    END_VERSIONS
    """
}
