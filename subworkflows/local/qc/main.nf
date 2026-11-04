// QC: fast metrics, slow images and an HTML report, split so a slow or failed image step
// does not cost the metrics. The metrics JSON is the machine-readable contract.

include { QC_METRICS } from '../../../modules/local/qc_metrics'
include { QC_IMAGES  } from '../../../modules/local/qc_images'
include { QC_REPORT  } from '../../../modules/local/qc_report'

workflow QC {
    take:
    ch_sdata         // channel: [ val(meta), path(sdata) ]
    ch_markers       // channel: [ val(meta), path(csv) ], or an empty channel
    ch_unsubtracted  // channel: [ val(meta), path(tif) ], or an empty channel
    ch_registration  // channel: [ val(meta), path(dir) ] Ashlar QC keyed by Ashlar's meta.id, or empty
    methods          // list: segmentation methods that ran; QC runs once per sample and method

    main:

    def ch_versions = channel.empty()

    // remainder: true keeps stores without a pre-subtraction image (no backsub) or marker
    // sheet (pre-stitched input); the missing side becomes [], meaning no flag in the module.
    def ch_sample_input = ch_sdata
        .join(ch_unsubtracted, remainder: true)
        .join(ch_markers, remainder: true)
        // Indexed, not destructured: a marker sheet with no store (upstream failure) is only [meta, null, csv].
        .filter { row -> row[1] != null }
        .map { meta, sdata, tif, markers -> [meta, sdata, tif ?: [], markers ?: []] }

    // Ashlar runs per sample, or per slide before dearraying, so match on id: a TMA core's
    // id is never its slide's, and the slide-level QC goes to MERGE_REPORT instead.
    // Matched once per sample, before the fan-out to methods, so each id has one row on each side.
    def ch_sample_registration = ch_sample_input
        .map { meta, _sdata, _tif, _markers -> [meta.id, meta] }
        .join(ch_registration.map { meta, dir -> [meta.id, dir] }, remainder: true)
        // Indexed, not destructured: remainder rows with no sample side are only [id, null, dir].
        .filter { row -> row[1] != null }
        .map { row -> [row[1], row.size() > 2 && row[2] ? row[2] : []] }

    // One row per sample and method; meta.table names the table the QC scripts read.
    // toString(): a GString key never equals a String one, which would break the joins below.
    def ch_qc_input = ch_sample_input.flatMap { meta, sdata, tif, markers ->
        methods.collect { method -> [meta + [method: method, table: "${method}_table".toString()], sdata, tif, markers] }
    }
    def ch_registration_input = ch_sample_registration.flatMap { meta, dir ->
        methods.collect { method -> [meta + [method: method, table: "${method}_table".toString()], dir] }
    }

    QC_METRICS(ch_qc_input)
    ch_versions = ch_versions.mix(QC_METRICS.out.versions)

    if (params.use_qc_images) {
        QC_IMAGES(ch_qc_input.map { meta, sdata, _tif, markers -> [meta, sdata, markers] })
        ch_versions = ch_versions.mix(QC_IMAGES.out.versions)
        ch_report_input = QC_METRICS.out.metrics.join(QC_IMAGES.out.images)
    }
    else {
        ch_report_input = QC_METRICS.out.metrics.map { meta, metrics -> [meta, metrics, []] }
    }

    // Same meta on both sides, so a plain join; every row has a registration entry ([] if none).
    ch_report_input = ch_report_input.join(ch_registration_input)

    QC_REPORT(ch_report_input)
    ch_versions = ch_versions.mix(QC_REPORT.out.versions)

    emit:
    metrics  = QC_METRICS.out.metrics  // channel: [ val(meta), path(json) ] the machine-readable contract
    report   = QC_REPORT.out.report    // channel: [ val(meta), path(html) ]
    versions = ch_versions             // channel: [ path(versions.yml) ]
}
