import { Injectable } from '@nestjs/common';
import * as crypto from 'crypto';

const ALGORITHM = 'aes-256-gcm';
const IV_LENGTH = 16;
const TAG_LENGTH = 16;
const SALT_LENGTH = 32;
const KEY_LENGTH = 32;
const ITERATIONS = 100000;

@Injectable()
export class EncryptionService {
  private getKey(salt: Buffer): Buffer {
    const secret = process.env.SESSION_SECRET || 'fallback-secret-key';
    return crypto.pbkdf2Sync(secret, salt, ITERATIONS, KEY_LENGTH, 'sha256');
  }

  encrypt(plaintext: string): string {
    const salt = crypto.randomBytes(SALT_LENGTH);
    const key = this.getKey(salt);
    const iv = crypto.randomBytes(IV_LENGTH);

    const cipher = crypto.createCipheriv(ALGORITHM, key, iv);
    const encrypted = Buffer.concat([
      cipher.update(plaintext, 'utf8'),
      cipher.final(),
    ]);
    const tag = cipher.getAuthTag();

    const combined = Buffer.concat([salt, iv, tag, encrypted]);
    return combined.toString('base64');
  }

  decrypt(ciphertext: string): string {
    const combined = Buffer.from(ciphertext, 'base64');

    const salt = combined.subarray(0, SALT_LENGTH);
    const iv = combined.subarray(SALT_LENGTH, SALT_LENGTH + IV_LENGTH);
    const tag = combined.subarray(SALT_LENGTH + IV_LENGTH, SALT_LENGTH + IV_LENGTH + TAG_LENGTH);
    const encrypted = combined.subarray(SALT_LENGTH + IV_LENGTH + TAG_LENGTH);

    const key = this.getKey(salt);
    const decipher = crypto.createDecipheriv(ALGORITHM, key, iv);
    decipher.setAuthTag(tag);

    const decrypted = Buffer.concat([
      decipher.update(encrypted),
      decipher.final(),
    ]);
    return decrypted.toString('utf8');
  }

  encryptConfig(config: Record<string, any>): Record<string, any> {
    const sensitiveKeys = ['client_secret', 'api_key', 'password', 'token', 'secret'];
    const encrypted: Record<string, any> = {};

    for (const [key, value] of Object.entries(config)) {
      const isSensitive = sensitiveKeys.some(sk => key.toLowerCase().includes(sk));
      if (isSensitive && typeof value === 'string' && value.length > 0) {
        encrypted[key] = { __encrypted: true, value: this.encrypt(value) };
      } else {
        encrypted[key] = value;
      }
    }
    return encrypted;
  }

  decryptConfig(config: Record<string, any>): Record<string, any> {
    const decrypted: Record<string, any> = {};

    for (const [key, value] of Object.entries(config)) {
      if (value && typeof value === 'object' && value.__encrypted === true) {
        try {
          decrypted[key] = this.decrypt(value.value);
        } catch {
          decrypted[key] = '';
        }
      } else {
        decrypted[key] = value;
      }
    }
    return decrypted;
  }

  maskConfig(config: Record<string, any>): Record<string, any> {
    const sensitiveKeys = ['client_secret', 'api_key', 'password', 'token', 'secret'];
    const masked: Record<string, any> = {};

    for (const [key, value] of Object.entries(config)) {
      const isSensitive = sensitiveKeys.some(sk => key.toLowerCase().includes(sk));
      if (isSensitive && typeof value === 'string' && value.length > 0) {
        masked[key] = '••••••••';
      } else if (value && typeof value === 'object' && value.__encrypted === true) {
        masked[key] = '••••••••';
      } else {
        masked[key] = value;
      }
    }
    return masked;
  }
}
