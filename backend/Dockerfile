# 1. Use an official Python runtime as a parent image
# We use 'slim' because it is smaller but still has apt-get (unlike alpine)
FROM python:3.10-slim

# 2. Set the working directory
WORKDIR /app

# 3. Install System Dependencies (The fix is here)
# - tesseract-ocr: For reading text from images
# - poppler-utils: For converting PDFs to images
# - libgl1: Required by OpenCV (cv2) - 'libgl1-mesa-glx' is deprecated
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 4. Copy the requirements file into the container
COPY requirements.txt .

# 5. Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy the rest of the application code
COPY . .

# 7. Expose the port (Documentation only)
EXPOSE 8000

# 8. Define the default command (can be overridden by docker-compose)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]