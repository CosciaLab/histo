process PATCH_SEGMENTATION_INSTANSEG {
    label "process_low"
    tag "${meta.sample}"

    conda "${moduleDir}/environment.yml"
    // Weights are baked into the image: no download at run time, and the cluster may be offline.
    container "docker.io/josenimo/sopa-seg:2.2.12"

    input:
    tuple val(meta), path(sdata_path), val(cli_arguments), val(index), val(n_patches)

    output:
    tuple val(meta), path(sdata_path), path("${index}.parquet"), val(n_patches)
    path "versions.yml"

    script:
    """
    sopa segmentation instanseg ${sdata_path} --patch-index ${index} ${cli_arguments}

    mv ${sdata_path}/.sopa_cache/instanseg_boundaries/${index}.parquet ${index}.parquet

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        sopa: \$(sopa --version)
        instanseg: \$(python -c "import importlib.metadata as m; print(m.version('instanseg-torch'))")
    END_VERSIONS
    """

    stub:
    """
    touch ${index}.parquet

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        sopa: stub
        instanseg: stub
    END_VERSIONS
    """
}
