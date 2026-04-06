package com.genai.springboot.dto;

public record FastApiUploadResponse(
        boolean success,
        String message,
        FastApiUploadData data
) {
}
