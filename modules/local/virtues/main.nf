process VIRTUES {
    label "process_medium"
    label "process_long"
    tag "${meta.sample}:virtues"

    conda "${moduleDir}/environment.yml"
    // Weights, ESM-2 and UniProt sequences are baked into the image: no download at run time.
    container "docker.io/josenimo/virtues:d2c25e1-2"

    input:
    // sdata_path is only read; spec.channels is [name, uniprot_id] pairs and spec.unembedded names, both resolved upstream.
    tuple val(meta), path(sdata_path), val(methods), val(spec), path(stats)

    output:
    tuple val(meta), path("*.{h5ad,parquet}")
    tuple val(meta), path("virtues.json")
    path "versions.yml"

    script:
    // FlashAttention has no CPU path: fail here with a clear message instead of deep in the tool.
    def gpu_check = task.accelerator ? """python -c "import torch; torch.ones(1, device='cuda').sum().item()" || { echo 'use_virtues: CUDA is not usable in this task' >&2; exit 1; }""" : """echo 'use_virtues: VIRTUES needs a GPU' >&2; exit 1"""
    def channels = spec.channels.collect { "${it[0]}:${it[1]}" }.join(',')
    """
    ${gpu_check}
    virtues_cells.py \\
        --sdata ${sdata_path} \\
        --methods '${methods.join(',')}' \\
        --channels '${channels}' \\
        --unembedded '${spec.unembedded.join(',')}' \\
        --stats ${stats} \\
        --pixel-size ${spec.pixel_size} \\
        --device cuda \\
        --outdir .

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        virtues: \$VIRTUES_COMMIT
        torch: \$(python -c "import torch; print(torch.__version__)")
        flash_attn: \$(python -c "import flash_attn; print(flash_attn.__version__)")
    END_VERSIONS
    """

    stub:
    def touches = methods.collect { "${it}_virtues.h5ad" }.join(' ')
    """
    echo "${task.accelerator ? 'gpu' : 'none'}" > .accelerator
    touch ${touches} virtues_niches.parquet virtues_niches_table.h5ad virtues_tissue.h5ad virtues.json

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        virtues: stub
        torch: stub
        flash_attn: stub
    END_VERSIONS
    """
}
