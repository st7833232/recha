import AVFoundation
import CoreVideo
import Foundation
import QuartzCore

struct Media: Decodable {
    let url: URL
    let header: [String: String]
}

func check(_ media: Media) -> Bool {
    let asset = AVURLAsset(url: media.url, options: ["AVURLAssetHTTPHeaderFieldsKey": media.header])
    let item = AVPlayerItem(asset: asset)
    let output = AVPlayerItemVideoOutput(pixelBufferAttributes: [
        kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA
    ])
    item.add(output)
    let player = AVPlayer(playerItem: item)
    player.isMuted = true
    player.play()
    defer { player.pause() }
    let deadline = Date().addingTimeInterval(65)
    var reachedStart = false
    var didSeek = false
    while Date() < deadline {
        RunLoop.current.run(until: Date().addingTimeInterval(0.075))
        if item.status == .failed {
            let error = item.error as NSError?
            print("AVPlayer error", error?.domain ?? "unknown", error?.code ?? 0)
            return false
        }
        let t = output.itemTime(forHostTime: CACurrentMediaTime())
        guard t.isNumeric, output.hasNewPixelBuffer(forItemTime: t),
              let frame = output.copyPixelBuffer(forItemTime: t, itemTimeForDisplay: nil) else { continue }
        let w = CVPixelBufferGetWidth(frame), h = CVPixelBufferGetHeight(frame)
        guard min(w, h) == 360 else { continue }
        if !reachedStart && t.seconds >= 0.35 {
            print("AVPlayer decoded", w, h, "at", t.seconds)
            reachedStart = true
            player.seek(to: CMTime(seconds: 5, preferredTimescale: 600),
                        toleranceBefore: .zero, toleranceAfter: .zero) { ok in didSeek = ok }
        } else if reachedStart && didSeek && t.seconds >= 5.25 {
            print("AVPlayer decoded after seek at", t.seconds)
            return true
        }
    }
    print("AVPlayer timeout, status", item.status.rawValue, "playhead", player.currentTime().seconds)
    return false
}

do {
    let payload = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
    exit(check(try JSONDecoder().decode(Media.self, from: payload)) ? 0 : 1)
} catch {
    print("Unable to load source response")
    exit(2)
}
