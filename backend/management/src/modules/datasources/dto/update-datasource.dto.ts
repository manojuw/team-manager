import { IsOptional, IsObject, IsString, IsNumber, IsBoolean } from 'class-validator';

export class UpdateDataSourceDto {
  @IsOptional()
  @IsString()
  sourceType?: string;

  @IsOptional()
  @IsObject()
  config?: Record<string, any>;

  @IsOptional()
  @IsNumber()
  syncIntervalMinutes?: number;

  @IsOptional()
  @IsBoolean()
  syncEnabled?: boolean;
}
