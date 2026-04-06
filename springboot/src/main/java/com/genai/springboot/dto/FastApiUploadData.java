package com.genai.springboot.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public record FastApiUploadData(
        @JsonProperty("file_name") String fileName,
        @JsonProperty("stored_path") String storedPath,
        @JsonProperty("size_in_bytes") long sizeInBytes
) {
}
