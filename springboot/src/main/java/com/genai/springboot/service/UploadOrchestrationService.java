package com.genai.springboot.service;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

import java.nio.file.Path;

@Service
public class UploadOrchestrationService {

    private final FastApiIngestService fastApiIngestService;
    private final UploadTrackingService uploadTrackingService;

    public UploadOrchestrationService(
            FastApiIngestService fastApiIngestService,
            UploadTrackingService uploadTrackingService
    ) {
        this.fastApiIngestService = fastApiIngestService;
        this.uploadTrackingService = uploadTrackingService;
    }

    @Async
    public void forwardAndStartProcessing(String fileId, Path localFilePath) {
        try {
            uploadTrackingService.setStatus(fileId, "FORWARDING");
            fastApiIngestService.uploadToIngest(localFilePath, fileId);
            fastApiIngestService.triggerProcessing(fileId);
            uploadTrackingService.setStatus(fileId, "PROCESSING");
        } catch (Exception ex) {
            uploadTrackingService.setFailure(fileId, ex.getMessage());
        }
    }
}
