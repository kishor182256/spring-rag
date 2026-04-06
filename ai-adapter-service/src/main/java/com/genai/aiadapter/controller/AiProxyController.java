package com.genai.aiadapter.controller;

import com.genai.aiadapter.service.FastApiProxyService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.bind.annotation.RequestPart;

import java.util.Map;

@RestController
@RequestMapping("/api/v1")
public class AiProxyController {

    private final FastApiProxyService fastApiProxyService;

    public AiProxyController(FastApiProxyService fastApiProxyService) {
        this.fastApiProxyService = fastApiProxyService;
    }

    @PostMapping("/chat/query")
    public Map<String, Object> chatQuery(@RequestBody Map<String, Object> payload) {
        return fastApiProxyService.forwardChatQuery(payload);
    }

    @PostMapping("/ingest/upload")
    public Map<String, Object> ingestUpload(
            @RequestPart("file") MultipartFile file,
            @RequestParam(name = "file_id", required = false) String fileId
    ) {
        return fastApiProxyService.forwardIngestUpload(file, fileId);
    }

    @PostMapping("/ingest/{fileId}/process")
    public Map<String, Object> ingestProcess(@PathVariable String fileId) {
        return fastApiProxyService.forwardIngestProcess(fileId);
    }

    @GetMapping("/ingest/{fileId}/status")
    public Map<String, Object> ingestStatus(@PathVariable String fileId) {
        return fastApiProxyService.forwardIngestStatus(fileId);
    }

    @GetMapping("/ingest/{fileId}/chunks")
    public Map<String, Object> ingestChunks(
            @PathVariable String fileId,
            @RequestParam(name = "offset", defaultValue = "0") int offset,
            @RequestParam(name = "limit", defaultValue = "10") int limit,
            @RequestParam(name = "include_text", defaultValue = "false") boolean includeText
    ) {
        return fastApiProxyService.forwardIngestChunks(fileId, offset, limit, includeText);
    }

    @GetMapping("/health/fastapi")
    public Map<String, Object> fastApiHealth() {
        return fastApiProxyService.forwardHealth();
    }
}