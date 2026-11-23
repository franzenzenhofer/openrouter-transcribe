// Records macOS system audio (everything the Mac plays, e.g. the Teams call) to an .mp4 via ScreenCaptureKit.
// Usage: swift sysaudio.swift <out.mp4>   Stop with SIGINT or SIGTERM; the file is finalised on stop.
// The file is fragmented MP4 (a fragment every 1 s), so even after SIGKILL, a crash or a stream error
// everything but the last few seconds is decodable (2026-11-23: a closed lid left an .m4a without its
// moov index). Sleep and wake are logged as "SLEEP <time>" / "WAKE <time>".
import AppKit
import AVFoundation
import Foundation
import ScreenCaptureKit

func log(_ message: String) {
    FileHandle.standardError.write("[sysaudio] \(message)\n".data(using: .utf8)!)
}

func stamp() -> String { ISO8601DateFormatter().string(from: Date()) }

final class Recorder: NSObject, SCStreamOutput, SCStreamDelegate {
    let writer: AVAssetWriter
    let input: AVAssetWriterInput
    var stream: SCStream?
    var started = false
    var finalised = false
    let queue = DispatchQueue(label: "sysaudio")

    init(url: URL) throws {
        writer = try AVAssetWriter(outputURL: url, fileType: .mp4)
        writer.movieFragmentInterval = CMTime(seconds: 1, preferredTimescale: 600)
        input = AVAssetWriterInput(mediaType: .audio, outputSettings: [
            AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: 48000,
            AVNumberOfChannelsKey: 2, AVEncoderBitRateKey: 128_000,
        ])
        input.expectsMediaDataInRealTime = true
        writer.add(input)
    }

    func start() async throws {
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
        guard let display = content.displays.first else { log("no display found (display asleep, or no Screen Recording permission)"); throw NSError(domain: "sysaudio", code: 1) }
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
        log("recording")
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sb: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .audio, sb.isValid else { return }
        if !started {
            writer.startWriting()
            writer.startSession(atSourceTime: sb.presentationTimeStamp)
            started = true
        }
        if !finalised, input.isReadyForMoreMediaData { input.append(sb) }
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        log("stopped with error: \(error) at \(stamp())")
        Task { await finalise(); exit(2) }
    }

    func finalise() async {
        await withCheckedContinuation { (c: CheckedContinuation<Void, Never>) in
            queue.async {
                if self.finalised || !self.started { c.resume(); return }
                self.finalised = true
                self.input.markAsFinished()
                self.writer.finishWriting { c.resume() }
            }
        }
        log("finalised")
    }

    func stop() async {
        try? await stream?.stopCapture()
        await finalise()
    }
}

let out = URL(fileURLWithPath: CommandLine.arguments[1])
let rec = try Recorder(url: out)
var sources: [DispatchSourceSignal] = []
for sigNo in [SIGINT, SIGTERM] {
    signal(sigNo, SIG_IGN)
    let src = DispatchSource.makeSignalSource(signal: sigNo, queue: .main)
    src.setEventHandler { Task { await rec.stop(); exit(0) } }
    src.resume()
    sources.append(src)
}
let center = NSWorkspace.shared.notificationCenter
center.addObserver(forName: NSWorkspace.willSleepNotification, object: nil, queue: .main) { _ in log("SLEEP \(stamp())") }
center.addObserver(forName: NSWorkspace.didWakeNotification, object: nil, queue: .main) { _ in log("WAKE \(stamp())") }
Task {
    do { try await rec.start() } catch {
        log("start failed: \(error)")
        exit(1)
    }
}
RunLoop.main.run()
