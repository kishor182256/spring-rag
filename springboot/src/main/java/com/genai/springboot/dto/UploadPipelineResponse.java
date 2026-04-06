package com.genai.springboot.dto;

public record UploadPipelineResponse(
        String fileId,
        String status,
        FileUploadResponse local,
        FastApiUploadData fastApi
) {
}
