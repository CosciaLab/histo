// Learned per-cell features for every spec (model) and segmentation method, then one write into the store per sample.

include { NIMBUS            } from '../../../modules/local/nimbus'
include { VIRTUES_HISTOGRAM } from '../../../modules/local/virtues_histogram'
include { VIRTUES_STATS     } from '../../../modules/local/virtues_stats'
include { VIRTUES           } from '../../../modules/local/virtues'
include { WRITE_FEATURES    } from '../../../modules/local/write_features'
include { defaultNimbusChannels; virtuesChannels; virtuesUnembedded } from '../../../modules/local/utils'

workflow LEARNED_FEATURES {
    take:
    ch_sdata   // channel: [ val(meta), path(sdata) ] the store with segmentations written
    ch_markers // channel: [ val(meta), path(csv) ] the channels each image has; empty without a marker sheet
    specs      // list: spec maps from featureSpecs(params), shared by every sample
    methods    // list: segmentation methods, each scored separately

    main:
    def ch_versions = channel.empty()

    // Samples are keyed by meta.sdata_dir as a String, as in SEGMENTATION (a GString never equals a String).

    // remainder: true keeps a sample with no sheet (sheet is null), so given channels can still be checked when one exists.
    def ch_sample_rows = ch_sdata
        .join(ch_markers, remainder: true)
        .map { meta, sdata, sheet -> [meta, sdata, sheet ? sheet.splitCsv(header: true) : null] }

    // Nimbus: one row per sample, method and spec. VirTues: one row per sample, carrying every method,
    // since it embeds the image once and pools per method. Specs are shared objects: build new maps, never mutate one.
    def ch_sample_specs = ch_sample_rows.flatMap { meta, sdata, rows ->
        specs.collectMany { spec ->
            if (spec.model == 'nimbus') {
                // Unknown names would fail inside the task; fail here and say which.
                if (rows != null && spec.channels) {
                    def missing = spec.channels - rows*.marker_name
                    if (missing) {
                        // error(), not assert: an assert inside an operator dies without its message.
                        error("Sample '${meta.sample}': nimbus_channels not in the marker sheet: ${missing.join(', ')}.")
                    }
                }
                def channels = spec.channels ?: defaultNimbusChannels(rows ?: [])
                if (!channels) {
                    error("Sample '${meta.sample}': no marker channels for nimbus. Set nimbus_channels, or mark channels 'marker' in the marker sheet.")
                }
                return methods.collect { method -> [meta, sdata, method, spec + [channels: channels]] }
            }
            if (spec.model == 'virtues') {
                def channels = virtuesChannels(rows ?: [])
                if (!channels) {
                    error("Sample '${meta.sample}': no marker row with a uniprot_id reached VirTues. With use_backsub, check that backsub kept the uniprot_id column.")
                }
                return [[meta, sdata, methods, spec + [channels: channels, unembedded: virtuesUnembedded(rows)]]]
            }
            // A model with no branch here would be dropped and the store never written: fail instead.
            error("Unknown learned-features model '${spec.model}'; add its branch to LEARNED_FEATURES.")
        }
    }

    // One branch per model; KRONOS and others add theirs here. The third item is a method for
    // Nimbus and the list of methods for VirTues.
    def ch_by_model = ch_sample_specs.branch { _meta, _sdata, _method, spec ->
        nimbus: spec.model == 'nimbus'
        virtues: spec.model == 'virtues'
    }

    (ch_nimbus, versions) = NIMBUS(ch_by_model.nimbus)
    ch_versions = ch_versions.mix(versions)

    // VirTues standardises intensities with slide-wide statistics: a TMA's cores share their slide's.
    // Slide key below: meta.slide on a TMA core, else the sample; a String, as a GString never equals one.
    def virtues_spec = specs.find { spec -> spec.model == 'virtues' }

    def ch_virtues_input
    if (virtues_spec?.stats) {
        // Given statistics replace both statistics tasks; the same file goes to every store.
        ch_virtues_input = ch_by_model.virtues
            .map { meta, sdata, store_methods, spec -> [meta, sdata, store_methods, spec, file(spec.stats)] }
    }
    else {
        (ch_hists, versions) = VIRTUES_HISTOGRAM(
            ch_by_model.virtues.map { meta, sdata, _methods, spec -> [meta, sdata, spec] }
        )
        ch_versions = ch_versions.mix(versions)

        // No size given: the cores per slide are not known in advance, so this waits for every store.
        def ch_slide_hists = ch_hists
            .map { meta, hist -> [(meta.slide ?: meta.sample).toString(), hist] }
            .groupTuple()
            // Sorted by file name, so -resume does not depend on arrival order.
            .map { slide, hists -> [slide, hists.sort(false) { hist -> hist.name }, virtues_spec] }

        (ch_stats, versions) = VIRTUES_STATS(ch_slide_hists)
        ch_versions = ch_versions.mix(versions)

        // combine by: 0, not join: join pairs one row per key, and a slide has many stores.
        ch_virtues_input = ch_by_model.virtues
            .map { meta, sdata, store_methods, spec -> [(meta.slide ?: meta.sample).toString(), meta, sdata, store_methods, spec] }
            .combine(ch_stats, by: 0)
            .map { _slide, meta, sdata, store_methods, spec, stats -> [meta, sdata, store_methods, spec, stats] }
    }

    (ch_virtues, _ch_virtues_provenance, versions) = VIRTUES(ch_virtues_input)
    ch_versions = ch_versions.mix(versions)

    // Every model's outputs, as [meta, [files]]; the writer needs no more. A single glob match is a bare path.
    def ch_outputs = ch_nimbus
        .map { meta, _method, _spec, table, _provenance -> [meta, [table]] }
        .mix(ch_virtues.map { meta, files -> [meta, files instanceof List ? files : [files]] })

    // groupKey carries the output count, so a sample is written once all its outputs are in.
    // Nimbus gives one table per method; VirTues one list of files per store.
    def n_outputs = specs.sum { spec -> spec.model == 'virtues' ? 1 : methods.size() }
    def ch_sample_outputs = ch_outputs
        .map { meta, files -> [groupKey(meta.sdata_dir.toString(), n_outputs), files] }
        .groupTuple()
        // Flattened and sorted by file name, so the write order and -resume do not depend on arrival order.
        .map { key, file_lists -> [key.toString(), file_lists.collectMany { files -> files }.sort { f -> f.name }] }

    // Outputs carry no store; take it back by sample. join: one row per sample on both sides.
    def ch_to_write = ch_sdata
        .map { meta, sdata -> [meta.sdata_dir.toString(), meta, sdata] }
        .join(ch_sample_outputs)
        .map { _sdata_dir, meta, sdata, files -> [meta, sdata, files] }

    (ch_written, versions) = WRITE_FEATURES(ch_to_write)
    ch_versions = ch_versions.mix(versions)

    emit:
    sdata    = ch_written  // channel: [ val(meta), path(sdata) ] with tables {method}_nimbus and {method}_virtues written
    versions = ch_versions // channel: [ path(versions.yml) ]
}
