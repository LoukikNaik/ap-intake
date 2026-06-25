FROM node:20-alpine

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

EXPOSE 5173
# Dev server (with hot reload) — simplest "one command up" for the demo.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
