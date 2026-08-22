import Foundation
import AVFoundation

public final class AudioCaptureManager: NSObject, @unchecked Sendable {
    private let audioEngine = AVAudioEngine()
    private var isRecording = false
    public var onAudioChunk: ((AudioChunk) -> Void)?
    
    public override init() {
        super.init()
    }
    
    public func startCapture() throws {
        guard !isRecording else { return }
        
        let inputNode = audioEngine.inputNode
        let format = inputNode.outputFormat(forBus: 0)
        
        // 16kHz モノラルへリサンプル設定の調整（必要に応じて）
        inputNode.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] (buffer, time) in
            guard let self = self else { return }
            let pcmData = self.convertBufferToData(buffer: buffer)
            let chunk = AudioChunk(data: pcmData, sampleRate: format.sampleRate, channels: Int(format.channelCount))
            self.onAudioChunk?(chunk)
        }
        
        audioEngine.prepare()
        try audioEngine.start()
        isRecording = true
    }
    
    public func stopCapture() {
        guard isRecording else { return }
        audioEngine.inputNode.removeTap(onBus: 0)
        audioEngine.stop()
        isRecording = false
    }
    
    private func convertBufferToData(buffer: AVAudioPCMBuffer) -> Data {
        let channelCount = Int(buffer.format.channelCount)
        let length = Int(buffer.frameLength)
        guard let floatData = buffer.floatChannelData else { return Data() }
        
        var int16Array = [Int16]()
        int16Array.reserveCapacity(length * channelCount)
        
        for frame in 0..<length {
            for channel in 0..<channelCount {
                let sample = floatData[channel][frame]
                let clipped = max(-1.0, min(1.0, sample))
                let int16Sample = Int16(clipped * 32767.0)
                int16Array.append(int16Sample)
            }
        }
        
        return Data(bytes: int16Array, count: int16Array.count * MemoryLayout<Int16>.size)
    }
}
