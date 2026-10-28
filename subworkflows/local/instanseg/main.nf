include { PATCH_SEGMENTATION_INSTANSEG } from '../../../modules/local/patch_segmentation_instanseg'
include { RESOLVE_INSTANSEG } from '../../../modules/local/resolve_instanseg'
include { argsCLI } from '../../../modules/local/utils'

workflow INSTANSEG {
    take:
    ch_patches

    main:
    ch_versions = channel.empty()

    instanseg_args = argsCLI("instanseg")

    ch_patches
        .map { meta, sdata_path, patches_file_image -> [meta, sdata_path, patches_file_image.text.trim().toInteger()] }
        .flatMap { meta, sdata_path, n_patches -> (0..<n_patches).collect { index -> [meta, sdata_path, instanseg_args, index, n_patches] } }
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
