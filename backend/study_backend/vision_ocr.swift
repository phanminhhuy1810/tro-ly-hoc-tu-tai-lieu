import Foundation
import Vision
import ImageIO
import AppKit
import PDFKit

// The parent normally cancels/terminates this helper. Also stop after a hard
// parent crash or a native framework hang; a detached helper must not live on.
let initialParent = getppid()
let nativeStarted = DispatchTime.now().uptimeNanoseconds
let watchdog = DispatchSource.makeTimerSource(queue: DispatchQueue.global(qos: .utility))
watchdog.schedule(deadline: .now() + .milliseconds(500), repeating: .milliseconds(500))
watchdog.setEventHandler {
    if getppid() != initialParent || DispatchTime.now().uptimeNanoseconds - nativeStarted > 50_000_000_000 {
        _exit(124)
    }
}
watchdog.resume()

func recognize(_ image: CGImage, locator: [String: Any]) throws -> [[String: Any]] {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = false
    let supported = try request.supportedRecognitionLanguages()
    let vietnamese = supported.first { $0.hasPrefix("vi-") }
    let preferred = [vietnamese, "en-US"].compactMap { $0 }.filter { supported.contains($0) }
    request.recognitionLanguages = preferred.isEmpty ? ["en-US"] : preferred
    let handler = VNImageRequestHandler(cgImage: image, options: [:])
    try handler.perform([request])
    return (request.results ?? []).compactMap { observation in
        guard let candidate = observation.topCandidates(1).first else { return nil }
        let box = observation.boundingBox
        return ["text": candidate.string, "locator": locator.merging([
            "bounds": [box.minX, box.minY, box.width, box.height],
            "bounds_coordinate_system": "normalized_bottom_left",
            "image_width": image.width, "image_height": image.height
        ]) { _, new in new }, "recognizer_score": candidate.confidence]
    }
}

func main() throws {
    let arguments = CommandLine.arguments
    if arguments.count == 2 && arguments[1] == "--languages" {
        let request = VNRecognizeTextRequest()
        let output: [String: Any] = ["languages": try request.supportedRecognitionLanguages(), "revision": request.revision]
        print(String(data: try JSONSerialization.data(withJSONObject: output), encoding: .utf8)!)
        return
    }
    if arguments.count == 3 && arguments[1] == "image-info" {
        let data = try Data(contentsOf: URL(fileURLWithPath: arguments[2]))
        guard let source = CGImageSourceCreateWithData(data as CFData, nil) else {
            throw NSError(domain: "OCR", code: 12, userInfo: [NSLocalizedDescriptionKey: "Invalid image source"])
        }
        let output: [String: Any] = ["frames": CGImageSourceGetCount(source)]
        print(String(data: try JSONSerialization.data(withJSONObject: output), encoding: .utf8)!)
        return
    }
    if arguments.count == 4 && arguments[1] == "image-frames" {
        let data = try Data(contentsOf: URL(fileURLWithPath: arguments[2]))
        guard let source = CGImageSourceCreateWithData(data as CFData, nil) else {
            throw NSError(domain: "OCR", code: 13, userInfo: [NSLocalizedDescriptionKey: "Invalid image source"])
        }
        let parts = arguments[3].split(separator: ",", omittingEmptySubsequences: false)
        let frames = parts.compactMap { Int($0) }
        guard frames.count == parts.count, frames.count >= 1 && frames.count <= 20,
              Set(frames).count == frames.count,
              frames.allSatisfy({ $0 >= 1 && $0 <= min(1000, CGImageSourceGetCount(source)) }) else {
            throw NSError(domain: "OCR", code: 14, userInfo: [NSLocalizedDescriptionKey: "Select up to 20 distinct existing image frames within 1 to 1000"])
        }
        for frame in frames {
            let index = frame - 1
            guard let properties = CGImageSourceCopyPropertiesAtIndex(source, index, nil) as? [CFString: Any],
                  let width = properties[kCGImagePropertyPixelWidth] as? NSNumber,
                  let height = properties[kCGImagePropertyPixelHeight] as? NSNumber,
                  width.doubleValue * height.doubleValue <= 25_000_000,
                  let image = CGImageSourceCreateThumbnailAtIndex(source, index,
                    [kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceCreateThumbnailWithTransform: true,
                     kCGImageSourceThumbnailMaxPixelSize: 2400] as CFDictionary) else {
                throw NSError(domain: "OCR", code: 15, userInfo: [NSLocalizedDescriptionKey: "Invalid or oversized frame"])
            }
            let values = try recognize(image, locator: ["type": "ocr_image", "frame": frame])
            let event: [String: Any] = ["kind": "frame", "frame": frame, "fragments": values,
                                      "engine": "macOS_Vision", "revision": VNRecognizeTextRequest().revision]
            print(String(data: try JSONSerialization.data(withJSONObject: event), encoding: .utf8)!)
            fflush(stdout)
        }
        print("{\"kind\":\"complete\"}")
        return
    }
    if arguments.count == 6 && arguments[1] == "render" {
        let data = try Data(contentsOf: URL(fileURLWithPath: arguments[3]))
        let pageLimit = 1000
        guard let pageNumber = Int(arguments[4]), pageNumber >= 1 && pageNumber <= pageLimit else {
            throw NSError(domain: "OCR", code: 5, userInfo: [NSLocalizedDescriptionKey: "Page/frame outside supported range"])
        }
        let image: CGImage
        if arguments[2] == "pdf" {
            guard let document = PDFDocument(data: data), !document.isLocked,
                  let page = document.page(at: pageNumber - 1) else {
                throw NSError(domain: "OCR", code: 6, userInfo: [NSLocalizedDescriptionKey: "Missing or locked PDF page"])
            }
            let rect = page.bounds(for: .mediaBox)
            let scale = min(2.5, 2400 / max(rect.width, rect.height))
            let thumbnail = page.thumbnail(of: NSSize(width: rect.width * scale, height: rect.height * scale), for: .mediaBox)
            guard let value = thumbnail.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
                throw NSError(domain: "OCR", code: 7, userInfo: [NSLocalizedDescriptionKey: "Cannot render PDF page"])
            }
            image = value
        } else {
            guard let source = CGImageSourceCreateWithData(data as CFData, nil), pageNumber <= CGImageSourceGetCount(source),
                  let properties = CGImageSourceCopyPropertiesAtIndex(source, pageNumber - 1, nil) as? [CFString: Any],
                  let width = properties[kCGImagePropertyPixelWidth] as? NSNumber,
                  let height = properties[kCGImagePropertyPixelHeight] as? NSNumber,
                  width.doubleValue * height.doubleValue <= 25_000_000,
                  let value = CGImageSourceCreateThumbnailAtIndex(source, pageNumber - 1, [kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceCreateThumbnailWithTransform: true, kCGImageSourceThumbnailMaxPixelSize: 2400] as CFDictionary) else {
                throw NSError(domain: "OCR", code: 8, userInfo: [NSLocalizedDescriptionKey: "Invalid or oversized image frame"])
            }
            image = value
        }
        guard let destination = CGImageDestinationCreateWithURL(URL(fileURLWithPath: arguments[5]) as CFURL, "public.png" as CFString, 1, nil) else {
            throw NSError(domain: "OCR", code: 9, userInfo: [NSLocalizedDescriptionKey: "Cannot create preview"])
        }
        CGImageDestinationAddImage(destination, image, nil)
        guard CGImageDestinationFinalize(destination) else {
            throw NSError(domain: "OCR", code: 10, userInfo: [NSLocalizedDescriptionKey: "Cannot save preview"])
        }
        print("{\"width\":\(image.width),\"height\":\(image.height)}")
        return
    }
    let selectedPDF = arguments.count == 4 && arguments[1] == "pdf-pages"
    guard (arguments.count == 3 && ["pdf", "image"].contains(arguments[1])) || selectedPDF else {
        throw NSError(domain: "OCR", code: 1, userInfo: [NSLocalizedDescriptionKey: "Expected format and input file"])
    }
    let data = try Data(contentsOf: URL(fileURLWithPath: arguments[2]))
    var fragments: [[String: Any]] = []
    var warnings: [String] = []
    let maxPages = 20
    if arguments[1] == "pdf" || selectedPDF {
        guard let document = PDFDocument(data: data), !document.isLocked else {
            throw NSError(domain: "OCR", code: 2, userInfo: [NSLocalizedDescriptionKey: "Invalid or locked PDF"])
        }
        var pages = Array(1...max(1, min(document.pageCount, maxPages)))
        if selectedPDF {
            let parts = arguments[3].split(separator: ",", omittingEmptySubsequences: false)
            pages = parts.compactMap { Int($0) }
            guard pages.count == parts.count, pages.count >= 1 && pages.count <= maxPages,
                  Set(pages).count == pages.count, pages.allSatisfy({ $0 >= 1 && $0 <= min(1000, document.pageCount) }) else {
                throw NSError(domain: "OCR", code: 11, userInfo: [NSLocalizedDescriptionKey: "Select up to 20 distinct existing PDF pages within 1 to 1000"])
            }
        }
        for number in pages {
            let index = number - 1
            guard let page = document.page(at: index) else { continue }
            let rect = page.bounds(for: .mediaBox)
            guard rect.width > 0 && rect.height > 0 else { continue }
            let scale = min(2.5, 2400 / max(rect.width, rect.height))
            let thumbnail = page.thumbnail(of: NSSize(width: rect.width * scale, height: rect.height * scale), for: .mediaBox)
            guard let image = thumbnail.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }
            let values = try recognize(image, locator: ["type": "ocr_page", "page": index + 1, "page_index_base": 1])
            if values.isEmpty { warnings.append("Trang \(index+1) chưa đọc được chữ; cần xem bản gốc hoặc nhập lại.") }
            if selectedPDF {
                let event: [String: Any] = ["kind": "page", "page": number, "fragments": values, "engine": "macOS_Vision", "revision": VNRecognizeTextRequest().revision]
                print(String(data: try JSONSerialization.data(withJSONObject: event), encoding: .utf8)!)
                fflush(stdout)
            } else { fragments.append(contentsOf: values) }
        }
        if !selectedPDF && document.pageCount > maxPages { warnings.append("OCR chỉ đọc 20 trang đầu trong lượt này; các trang còn lại chưa đọc.") }
    } else {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil) else {
            throw NSError(domain: "OCR", code: 3, userInfo: [NSLocalizedDescriptionKey: "Invalid image"])
        }
        let count = CGImageSourceGetCount(source)
        for index in 0..<min(count, maxPages) {
            guard let properties = CGImageSourceCopyPropertiesAtIndex(source, index, nil) as? [CFString: Any],
                  let width = properties[kCGImagePropertyPixelWidth] as? NSNumber,
                  let height = properties[kCGImagePropertyPixelHeight] as? NSNumber,
                  width.doubleValue * height.doubleValue <= 25_000_000 else {
                throw NSError(domain: "OCR", code: 4, userInfo: [NSLocalizedDescriptionKey: "Image too large; limit 25 million pixels"])
            }
            let options: [CFString: Any] = [kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceCreateThumbnailWithTransform: true, kCGImageSourceThumbnailMaxPixelSize: 2400]
            guard let image = CGImageSourceCreateThumbnailAtIndex(source, index, options as CFDictionary) else { continue }
            fragments.append(contentsOf: try recognize(image, locator: ["type": "ocr_image", "frame": index+1]))
        }
        if count > maxPages { warnings.append("Chỉ OCR 20 ảnh đầu của file nhiều ảnh; phần còn lại chưa đọc.") }
    }
    warnings.append("OCR nhận dạng chữ, chưa chứng minh công thức/bảng/sơ đồ đúng. Đối chiếu ảnh và sửa bản trích trước khi tạo.")
    let output: [String: Any] = ["kind": "complete", "fragments": fragments, "warnings": warnings, "engine": "macOS_Vision", "revision": VNRecognizeTextRequest().revision]
    print(String(data: try JSONSerialization.data(withJSONObject: output), encoding: .utf8)!)
}

do { try main() }
catch {
    let data = try! JSONSerialization.data(withJSONObject: ["error": error.localizedDescription])
    print(String(data: data, encoding: .utf8)!)
    exit(1)
}
