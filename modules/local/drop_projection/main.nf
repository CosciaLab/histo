process DROP_PROJECTION {
    label "process_single"
    tag "${meta.sample}"

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine in ['singularity', 'apptainer'] && !task.ext.singularity_pull_docker_container
?         'https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/70/707825bb6afa202806406063665a361b2a4a2fc6d6f802132359407408826ffe/data'
:         'community.wave.seqera.io/library/python_sopa:54a97bc5a187152d' }"

    input:
    tuple val(meta), path(sdata_path)

    output:
    // Mutates the store in place: AGGREGATE and QC then read the full marker image.
    tuple val(meta), path(sdata_path), emit: sdata
    path "versions.yml"              , emit: versions

    script:
    def args = task.ext.args ?: ""
    """
    project_channels.py drop --sdata ${sdata_path} ${args}

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        spatialdata: \$(python -c "import spatialdata; print(spatialdata.__version__)" 2> /dev/null)
    END_VERSIONS
    """

    stub:
    """
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        spatialdata: stub
    END_VERSIONS
    """
}
