import { IsOptional, IsObject, IsString, IsNumber, IsBoolean } from 'class-validator';

export class UpdateDataSourceDto {
  @IsOptional()
  @IsString()
  source_type?: string;

  @IsOptional()
  @IsObject()
  config?: Record<string, any>;

  @IsOptional()
  @IsNumber()
  sync_interval_minutes?: number;

  @IsOptional()
  @IsBoolean()
  sync_enabled?: boolean;
}
