// Records macOS system audio (everything the Mac plays, e.g. the Teams call) to an .m4a via ScreenCaptureKit.
// Usage: swift sysaudio.swift <out.m4a>   Stop with SIGINT (kill -INT pid); the file is finalised on stop.
import AVFoundation
import Foundation
import ScreenCaptureKit

final class Recorder: NSObject, SCStreamOutput, SCStreamDelegate {
    let writer: AVAssetWriter
    let input: AVAssetWriterInput
    var stream: SCStream?
    var started = false
    let queue = DispatchQueue(label: "sysaudio")

    init(url: URL) throws {
        writer = try AVAssetWriter(outputURL: url, fileType: .m4a)
        input = AVAssetWriterInput(mediaType: .audio, outputSettings: [
            AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: 48000,
            AVNumberOfChannelsKey: 2, AVEncoderBitRateKey: 128_000,
        ])
        input.expectsMediaDataInRealTime = true
        writer.add(input)
    }

    func start() async throws {
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
        guard let display = content.displays.first else { throw NSError(domain: "sysaudio", code: 1) }
        let filter = SCContentFilter(display: display, excludingWindows: [])
        let cfg = SCStreamConfiguration()
        cfg.capturesAudio = true
        cfg.excludesCurrentProcessAudio = true
        cfg.sampleRate = 48000
        cfg.channelCount = 2
        cfg.width = 2
        cfg.height = 2
        cfg.minimumFrameInterval = CMTime(value: 1, timescale: 1)
        let s = SCStream(filter: filter, configuration: cfg, delegate: self)
        try s.addStreamOutput(self, type: .audio, sampleHandlerQueue: queue)
        try await s.startCapture()
        stream = s
        FileHandle.standardError.write("[sysaudio] recording\n".data(using: .utf8)!)
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sb: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .audio, sb.isValid else { return }
        if !started {
            writer.startWriting()
            writer.startSession(atSourceTime: sb.presentationTimeStamp)
            started = true
        }
        if input.isReadyForMoreMediaData { input.append(sb) }
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        FileHandle.standardError.write("[sysaudio] stopped with error: \(error)\n".data(using: .utf8)!)
        exit(2)
    }

    func stop() async {
        try? await stream?.stopCapture()
        await withCheckedContinuation { (c: CheckedContinuation<Void, Never>) in
            queue.async {
                if self.started { self.input.markAsFinished(); self.writer.finishWriting { c.resume() } } else { c.resume() }
            }
        }
        FileHandle.standardError.write("[sysaudio] finalised\n".data(using: .utf8)!)
    }
}

let out = URL(fileURLWithPath: CommandLine.arguments[1])
let rec = try Recorder(url: out)
signal(SIGINT, SIG_IGN)
let sig = DispatchSource.makeSignalSource(signal: SIGINT, queue: .main)
sig.setEventHandler { Task { await rec.stop(); exit(0) } }
sig.resume()
Task {
    do { try await rec.start() } catch {
        FileHandle.standardError.write("[sysaudio] start failed: \(error)\n".data(using: .utf8)!)
        exit(1)
    }
}
dispatchMain()
