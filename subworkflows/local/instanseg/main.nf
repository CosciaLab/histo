include { PATCH_SEGMENTATION_INSTANSEG } from '../../../modules/local/patch_segmentation_instanseg'
include { RESOLVE_INSTANSEG } from '../../../modules/local/resolve_instanseg'
include { argsCLI; defaultInstansegChannels; getChannels; instansegMaxPatchWidth; instansegMemoryGB; stringifyItem } from '../../../modules/local/utils'

workflow INSTANSEG {
    take:
    ch_patches
    ch_markers // channel: [ val(meta), path(csv) ] the channels each image has; empty without a marker sheet

    main:
    ch_versions = channel.empty()

    instanseg_args = argsCLI("instanseg")

    // Unset instanseg_channels: take them from each sample's marker sheet. validateParams
    // guarantees a sheet exists in that case.
    if (params.instanseg_channels == null) {
        ch_with_args = ch_patches.join(ch_markers).map { meta, sdata_path, patches_file_image, sheet ->
            def channels = defaultInstansegChannels(sheet.splitCsv(header: true), params.instanseg_target)
            assert channels : "Sample '${meta.sample}': no channels for InstanSeg. Set instanseg_channels, or give the marker sheet a 'dna' channel."
            [meta, sdata_path, patches_file_image, "${instanseg_args} ${stringifyItem('channels', channels)}", channels.size()]
        }
    }
    else {
        def n_channels = getChannels(params.instanseg_channels).size()
        ch_with_args = ch_patches.map { meta, sdata_path, patches_file_image -> [meta, sdata_path, patches_file_image, instanseg_args, n_channels] }
    }

    // Above this a patch task waits long for a node, and its retry may exceed any.
    def warn_gb = 64
    ch_with_args
        .map { _meta, _sdata_path, _patches_file_image, _cli_args, n_channels -> n_channels }
        .unique()
        .subscribe { n_channels ->
            def gigabytes = instansegMemoryGB(n_channels, params.patch_width_pixel, params.instanseg_pixel_size)
            if (gigabytes > warn_gb) {
                log.warn "InstanSeg on ${n_channels} channels asks for ${gigabytes} GB per patch task (twice that on retry) " +
                    "at patch_width_pixel ${params.patch_width_pixel} and ${params.instanseg_pixel_size} µm/px. To stay under ${warn_gb} GB, " +
                    "set patch_width_pixel to ${instansegMaxPatchWidth(n_channels, warn_gb, params.instanseg_pixel_size)} or name fewer instanseg_channels."
            }
        }

    ch_with_args
        .map { meta, sdata_path, patches_file_image, cli_args, n_channels ->
            def memory_gb = instansegMemoryGB(n_channels, params.patch_width_pixel, params.instanseg_pixel_size)
            [meta, sdata_path, patches_file_image.text.trim().toInteger(), cli_args, memory_gb]
        }
        .flatMap { meta, sdata_path, n_patches, cli_args, memory_gb -> (0..<n_patches).collect { index -> [meta, sdata_path, cli_args, index, n_patches, memory_gb] } }
        .set { ch_instanseg }

    (ch_patch_segmented, versions) = PATCH_SEGMENTATION_INSTANSEG(ch_instanseg)
    ch_versions = ch_versions.mix(versions)

    ch_segmented = ch_patch_segmented
        .map { meta, sdata_path, parquet, n_patches -> [groupKey(meta.sdata_dir, n_patches), meta, sdata_path, parquet] }
        .groupTuple().map { _key, metas, sdata_paths, parquets -> [metas[0], sdata_paths[0], parquets] }

    (ch_resolved, versions) = RESOLVE_INSTANSEG(ch_segmented)

    ch_versions = ch_versions.mix(versions)

    emit:
    ch_resolved
    ch_versions
}
