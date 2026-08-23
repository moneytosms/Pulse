FROM node:24-slim

WORKDIR /app

# ponytail: relies on frontend track landing package-lock.json; build is a no-op error until then.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]
