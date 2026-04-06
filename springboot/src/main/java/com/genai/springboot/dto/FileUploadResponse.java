package com.genai.springboot.dto;

public record FileUploadResponse(
        String fileName,
        String storedAt,
        long sizeInBytes
) {
}
