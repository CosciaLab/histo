// Segmentation for every spec (method x target), tiled: one task per patch, then resolve,
// aggregate per method, and one write into the store per sample.

// One module under two names, so config selectors, GPU and memory stay per method and the
// trace names the method.
include { SEGMENT_PATCH as SEGMENT_PATCH_CELLPOSE  } from '../../../modules/local/segment_patch'
include { SEGMENT_PATCH as SEGMENT_PATCH_INSTANSEG } from '../../../modules/local/segment_patch'
include { RESOLVE                                  } from '../../../modules/local/resolve'
include { AGGREGATE                                } from '../../../modules/local/aggregate'
include { WRITE_SEGMENTATIONS                      } from '../../../modules/local/write_segmentations'
include { defaultInstansegChannels; instansegMaxPatchWidth; instansegMemoryGB } from '../../../modules/local/utils'

workflow SEGMENTATION {
    take:
    ch_patches // channel: [ val(meta), path(sdata), path(patches_file) ] the store and its patch count
    ch_markers // channel: [ val(meta), path(csv) ] the channels each image has; empty without a marker sheet
    specs      // list: spec maps from segmentationSpecs(params), shared by every sample

    main:
    def ch_versions = channel.empty()

    // Samples are keyed by meta.sdata_dir as a String: it is built as a GString, and a GString
    // never equals the same text as a String, so mixed keys would silently fail to match.

    // InstanSeg without instanseg_channels takes them from each sample's marker sheet;
    // validateParams guarantees a sheet exists then. Otherwise no join, as pre-stitched input has none.
    def needs_sheet = specs.any { spec -> spec.method == 'instanseg' && spec.channels == null }
    def ch_sample_rows = needs_sheet
        ? ch_patches.join(ch_markers).map { meta, sdata, patches_file, sheet -> [meta, sdata, patches_file, sheet.splitCsv(header: true)] }
        : ch_patches.map { meta, sdata, patches_file -> [meta, sdata, patches_file, []] }

    // One row per sample and spec. Specs are shared objects: build new maps, never mutate one.
    def ch_sample_specs = ch_sample_rows.flatMap { meta, sdata, patches_file, rows ->
        def n_patches = patches_file.text.trim().toInteger()
        // 0 patches would create no task, and the sample would vanish from the outputs silently.
        if (n_patches == 0) {
            error("Sample '${meta.sample}': 0 image patches, nothing to segment. Tissue segmentation may have found no tissue " +
                "(check the image, or set use_tissue_segmentation to false), or patch_width_pixel is larger than the image.")
        }
        specs.collect { spec ->
            if (spec.method != 'instanseg') {
                return [meta, sdata, spec, n_patches]
            }
            def channels = spec.channels ?: defaultInstansegChannels(rows, spec.target)
            if (!channels) {
                // error(), not assert: an assert inside an operator dies without its message.
                error("Sample '${meta.sample}': no channels for ${spec.name}. Set instanseg_channels, or give the marker sheet a 'dna' channel.")
            }
            // Memory per spec, as channel counts differ; conf/base.config reads spec.memory_gb.
            def memory_gb = instansegMemoryGB(channels.size(), params.patch_width_pixel, params.instanseg_pixel_size)
            [meta, sdata, spec + [channels: channels, memory_gb: memory_gb], n_patches]
        }
    }

    // Above this a patch task waits long for a node, and its retry may exceed any.
    def warn_gb = 64
    ch_sample_specs
        .filter { _meta, _sdata, spec, _n_patches -> spec.method == 'instanseg' }
        .map { _meta, _sdata, spec, _n_patches -> spec.channels.size() }
        .unique()
        .subscribe { n_channels ->
            def gigabytes = instansegMemoryGB(n_channels, params.patch_width_pixel, params.instanseg_pixel_size)
            if (gigabytes > warn_gb) {
                log.warn "InstanSeg on ${n_channels} channels asks for ${gigabytes} GB per patch task (twice that on retry) " +
                    "at patch_width_pixel ${params.patch_width_pixel} and ${params.instanseg_pixel_size} µm/px. To stay under ${warn_gb} GB, " +
                    "set patch_width_pixel to ${instansegMaxPatchWidth(n_channels, warn_gb, params.instanseg_pixel_size)} or name fewer instanseg_channels."
            }
        }

    // One task per spec and patch.
    def ch_patch_tasks = ch_sample_specs
        .flatMap { meta, sdata, spec, n_patches ->
            (0..<n_patches).collect { index -> [meta, sdata, spec, index, n_patches] }
        }
        .branch { _meta, _sdata, spec, _index, _n_patches ->
            cellpose: spec.method == 'cellpose'
            instanseg: spec.method == 'instanseg'
        }

    (ch_cellpose_parquets, versions) = SEGMENT_PATCH_CELLPOSE(ch_patch_tasks.cellpose)
    ch_versions = ch_versions.mix(versions)
    (ch_instanseg_parquets, versions) = SEGMENT_PATCH_INSTANSEG(ch_patch_tasks.instanseg)
    ch_versions = ch_versions.mix(versions)

    // groupKey carries the patch count, so groupTuple emits a spec's patches as soon as all have
    // arrived instead of waiting for every sample.
    def ch_spec_patches = ch_cellpose_parquets
        .mix(ch_instanseg_parquets)
        .map { meta, spec, parquet, n_patches -> [groupKey([meta.sdata_dir.toString(), spec.name], n_patches), meta, spec, parquet] }
        .groupTuple()
        // Sorted by patch index: the order sets how cells are numbered, so a rerun gives the same ids.
        .map { _key, metas, spec_list, parquets ->
            [metas[0].sdata_dir.toString(), metas[0], spec_list[0], parquets.sort(false) { parquet -> parquet.baseName.toInteger() }]
        }

    // Patch outputs carry no store; take it back by sample. combine, not join: one store meets
    // each of its specs, and join would pair a key only once.
    def ch_stores = ch_patches.map { meta, sdata, _patches_file -> [meta.sdata_dir.toString(), sdata] }
    def ch_to_resolve = ch_stores
        .combine(ch_spec_patches, by: 0)
        .map { _sdata_dir, sdata, meta, spec, parquets -> [meta, sdata, spec, parquets] }

    (ch_resolved, versions) = RESOLVE(ch_to_resolve)
    ch_versions = ch_versions.mix(versions)

    // One AGGREGATE per sample and method, once all of that method's specs are resolved.
    def ch_method_shapes = ch_resolved
        .map { meta, spec, parquet ->
            def n_specs = specs.count { s -> s.method == spec.method }
            [groupKey([meta.sdata_dir.toString(), spec.method], n_specs), meta, spec, parquet]
        }
        .groupTuple()
        // Sorted by spec name, so the task inputs, and with them -resume, do not depend on arrival order.
        .map { _key, metas, spec_list, parquets ->
            def pairs = [spec_list, parquets].transpose().sort { pair -> pair[0].name }
            [metas[0].sdata_dir.toString(), metas[0], spec_list[0].method, pairs*.get(0), pairs*.get(1)]
        }

    def ch_to_aggregate = ch_stores
        .combine(ch_method_shapes, by: 0)
        .map { _sdata_dir, sdata, meta, method, method_specs, shapes -> [meta, sdata, method, method_specs, shapes] }

    (ch_tables, versions) = AGGREGATE(ch_to_aggregate)
    ch_versions = ch_versions.mix(versions)

    // Each table with its method's shapes, joined on [sample, method]; both sides have one row per key.
    def ch_method_outputs = ch_tables
        .map { meta, method, table -> [[meta.sdata_dir.toString(), method], table] }
        .join(ch_method_shapes.map { sdata_dir, _meta, method, _method_specs, shapes -> [[sdata_dir, method], shapes] })

    // Then every method of a sample together, for its one write into the store.
    def n_methods = specs*.method.unique().size()
    def ch_sample_outputs = ch_method_outputs
        .map { key, table, shapes -> [groupKey(key[0], n_methods), key[0], table, shapes] }
        .groupTuple()
        // Sorted by table name, so the write order and -resume do not depend on arrival order.
        .map { _key, sdata_dirs, tables, shapes ->
            def pairs = [tables, shapes].transpose().sort { pair -> pair[0].name }
            [sdata_dirs[0], pairs.collectMany { pair -> pair[1] }, pairs*.get(0)]
        }

    def ch_to_write = ch_patches
        .map { meta, sdata, _patches_file -> [meta.sdata_dir.toString(), meta, sdata] }
        .join(ch_sample_outputs)
        .map { _sdata_dir, meta, sdata, shapes, tables -> [meta, sdata, shapes, tables] }

    (ch_written, versions) = WRITE_SEGMENTATIONS(ch_to_write)
    ch_versions = ch_versions.mix(versions)

    emit:
    sdata    = ch_written  // channel: [ val(meta), path(sdata) ] with shapes {method}_{target} and tables {method}_table
    versions = ch_versions // channel: [ path(versions.yml) ]
}
