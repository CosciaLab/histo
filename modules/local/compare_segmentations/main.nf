process COMPARE_SEGMENTATIONS {
    // Reads the store after WRITE_SEGMENTATIONS, beside QC; writes nothing into it.
    label "process_low"
    tag "${meta.sample}"

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine in ['singularity', 'apptainer'] && !task.ext.singularity_pull_docker_container
?         'https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/70/707825bb6afa202806406063665a361b2a4a2fc6d6f802132359407408826ffe/data'
:         'community.wave.seqera.io/library/python_sopa:54a97bc5a187152d' }"

    input:
    tuple val(meta), path(sdata_path)

    output:
    tuple val(meta), path("${meta.sample}_comparison.json"), emit: json
    tuple val(meta), path("${meta.sample}_comparison.html"), emit: html
    path "versions.yml"                                    , emit: versions

    script:
    def args = task.ext.args ?: ""
    """
    compare_segmentations.py \\
        --sdata ${sdata_path} \\
        --prefix ${meta.sample} \\
        ${args}

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: \$(python --version | sed 's/Python //')
        geopandas: \$(python -c "import geopandas; print(geopandas.__version__)")
        shapely: \$(python -c "import shapely; print(shapely.__version__)")
    END_VERSIONS
    """

    stub:
    """
    echo '{"sample": "${meta.sample}", "stub": true}' > ${meta.sample}_comparison.json
    touch ${meta.sample}_comparison.html

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: stub
        geopandas: stub
        shapely: stub
    END_VERSIONS
    """
}
