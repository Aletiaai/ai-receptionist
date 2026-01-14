FROM python:3.12-slim

   WORKDIR /app

   # Install dependencies
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt

   # Copy application
   COPY server.py .

   # Expose port
   EXPOSE 8080

   # Run server
   CMD ["python", "server.py"]