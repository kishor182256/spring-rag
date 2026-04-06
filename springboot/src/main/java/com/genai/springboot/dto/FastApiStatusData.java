package com.genai.springboot.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public record FastApiStatusData(
        @JsonProperty("file_id") String fileId,
        String status
) {
}
