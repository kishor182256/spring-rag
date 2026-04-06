package com.genai.springboot.dto;

public record FastApiStatusResponse(
        boolean success,
        String message,
        FastApiStatusData data
) {
}
