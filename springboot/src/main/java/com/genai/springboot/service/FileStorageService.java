package com.genai.springboot.service;

import com.genai.springboot.exception.FileStorageException;
import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.UUID;

@Service
public class FileStorageService {

    private final String uploadDir;
    private Path uploadPath;

    public FileStorageService(@Value("${app.storage.upload-dir}") String uploadDir) {
        this.uploadDir = uploadDir;
    }

    @PostConstruct
    public void init() {
        try {
            this.uploadPath = Paths.get(uploadDir).toAbsolutePath().normalize();
            Files.createDirectories(this.uploadPath);
        } catch (IOException ex) {
            throw new FileStorageException("Could not initialize upload directory", ex);
        }
    }

    public Path store(MultipartFile file) {
        if (file == null || file.isEmpty()) {
            throw new FileStorageException("Uploaded file is empty");
        }

        String originalFileName = file.getOriginalFilename();
        String safeName = (originalFileName == null || originalFileName.isBlank())
                ? "file"
                : Paths.get(originalFileName).getFileName().toString();

        String storedFileName = UUID.randomUUID() + "_" + safeName;
        Path target = uploadPath.resolve(storedFileName);

        try (InputStream inputStream = file.getInputStream()) {
            Files.copy(inputStream, target, StandardCopyOption.REPLACE_EXISTING);
            return target;
        } catch (IOException ex) {
            throw new FileStorageException("Failed to store file", ex);
        }
    }
}
