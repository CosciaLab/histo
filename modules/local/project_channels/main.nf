process PROJECT_CHANNELS {
    label "process_medium"
    tag "${meta.sample}"

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine in ['singularity', 'apptainer'] && !task.ext.singularity_pull_docker_container
?         'https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/70/707825bb6afa202806406063665a361b2a4a2fc6d6f802132359407408826ffe/data'
:         'community.wave.seqera.io/library/python_sopa:54a97bc5a187152d' }"

    input:
    // markers is in the tuple so it joins to its own store by key, not broadcast.
    tuple val(meta), path(sdata_path), path(markers)

    output:
    // Mutates the store in place: adds <image>_projected and points segmentation at it.
    tuple val(meta), path(sdata_path)                 , emit: sdata
    tuple val(meta), path("*_projection.{png,json}")  , emit: preview
    path "versions.yml"                               , emit: versions

    script:
    def args = task.ext.args ?: ""
    def prefix = task.ext.prefix ?: "${meta.id}"
    """
    project_channels.py project \\
        --sdata ${sdata_path} \\
        --markers ${markers} \\
        --prefix ${prefix} \\
        ${args}

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        spatialdata: \$(python -c "import spatialdata; print(spatialdata.__version__)" 2> /dev/null)
    END_VERSIONS
    """

    stub:
    def prefix = task.ext.prefix ?: "${meta.id}"
    """
    touch ${prefix}_projection.png
    touch ${prefix}_projection.json

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        spatialdata: stub
    END_VERSIONS
    """
}
