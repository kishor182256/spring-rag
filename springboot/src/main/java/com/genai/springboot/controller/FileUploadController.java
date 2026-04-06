package com.genai.springboot.controller;

import com.genai.springboot.dto.ApiResponse;
import com.genai.springboot.dto.FileStatusResponse;
import com.genai.springboot.dto.FileUploadResponse;
import com.genai.springboot.dto.UploadPipelineResponse;
import com.genai.springboot.exception.FileStorageException;
import com.genai.springboot.exception.ResourceNotFoundException;
import com.genai.springboot.service.FastApiIngestService;
import com.genai.springboot.service.FileStorageService;
import com.genai.springboot.service.UploadOrchestrationService;
import com.genai.springboot.service.UploadTrackingService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.nio.file.Path;
import java.util.UUID;

@RestController
@RequestMapping("/api/v1/files")
public class FileUploadController {

    private final FileStorageService fileStorageService;
    private final FastApiIngestService fastApiIngestService;
    private final UploadOrchestrationService uploadOrchestrationService;
    private final UploadTrackingService uploadTrackingService;

    public FileUploadController(
            FileStorageService fileStorageService,
            FastApiIngestService fastApiIngestService,
            UploadOrchestrationService uploadOrchestrationService,
            UploadTrackingService uploadTrackingService
    ) {
        this.fileStorageService = fileStorageService;
        this.fastApiIngestService = fastApiIngestService;
        this.uploadOrchestrationService = uploadOrchestrationService;
        this.uploadTrackingService = uploadTrackingService;
    }

    @PostMapping(value = "/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ApiResponse<UploadPipelineResponse> upload(@RequestParam("file") MultipartFile file) {
        if (file == null) {
            throw new FileStorageException("File is required");
        }

        String fileId = UUID.randomUUID().toString();
        Path storedFilePath = fileStorageService.store(file);
        uploadTrackingService.setStatus(fileId, "UPLOADED");
        uploadOrchestrationService.forwardAndStartProcessing(fileId, storedFilePath);

        FileUploadResponse localResponse = new FileUploadResponse(
                file.getOriginalFilename(),
                storedFilePath.toString(),
                file.getSize()
        );

        UploadPipelineResponse response = new UploadPipelineResponse(
                fileId,
                "UPLOADED",
                localResponse,
                null
        );
        return ApiResponse.success("File uploaded locally. FastAPI processing started asynchronously.", response);
    }

    @GetMapping("/{id}/status")
    public ApiResponse<FileStatusResponse> getStatus(@PathVariable("id") String fileId) {
        if (!uploadTrackingService.exists(fileId)) {
            throw new ResourceNotFoundException("File id not found: " + fileId);
        }

        String trackedStatus = uploadTrackingService.getStatus(fileId);
        if ("FAILED".equals(trackedStatus)) {
            String reason = uploadTrackingService.getFailureReason(fileId);
            return ApiResponse.success(
                    "File status fetched: " + (reason == null ? "Processing failed" : reason),
                    new FileStatusResponse(fileId, "FAILED")
            );
        }

        if ("UPLOADED".equals(trackedStatus) || "FORWARDING".equals(trackedStatus)) {
            return ApiResponse.success(
                    "File status fetched successfully",
                    new FileStatusResponse(fileId, trackedStatus)
            );
        }

        String status;
        try {
            status = fastApiIngestService.fetchProcessingStatus(fileId);
        } catch (ResourceNotFoundException ex) {
            status = "PROCESSING";
        }
        return ApiResponse.success(
                "File status fetched successfully",
                new FileStatusResponse(fileId, status)
        );
    }

    @GetMapping("/{id}/chunks")
    public ApiResponse<Object> getChunks(
            @PathVariable("id") String fileId,
            @RequestParam(name = "offset", defaultValue = "0") int offset,
            @RequestParam(name = "limit", defaultValue = "10") int limit,
            @RequestParam(name = "includeText", defaultValue = "false") boolean includeText
    ) {
        if (!uploadTrackingService.exists(fileId)) {
            throw new ResourceNotFoundException("File id not found: " + fileId);
        }

        Object chunks = fastApiIngestService.fetchChunks(fileId, offset, limit, includeText);
        return ApiResponse.success("File chunks fetched successfully", chunks);
    }
}
