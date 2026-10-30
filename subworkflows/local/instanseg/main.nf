include { PATCH_SEGMENTATION_INSTANSEG } from '../../../modules/local/patch_segmentation_instanseg'
include { RESOLVE_INSTANSEG } from '../../../modules/local/resolve_instanseg'
include { argsCLI; defaultInstansegChannels; stringifyItem } from '../../../modules/local/utils'

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
            [meta, sdata_path, patches_file_image, "${instanseg_args} ${stringifyItem('channels', channels)}"]
        }
    }
    else {
        ch_with_args = ch_patches.map { meta, sdata_path, patches_file_image -> [meta, sdata_path, patches_file_image, instanseg_args] }
    }

    ch_with_args
        .map { meta, sdata_path, patches_file_image, cli_args -> [meta, sdata_path, patches_file_image.text.trim().toInteger(), cli_args] }
        .flatMap { meta, sdata_path, n_patches, cli_args -> (0..<n_patches).collect { index -> [meta, sdata_path, cli_args, index, n_patches] } }
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
