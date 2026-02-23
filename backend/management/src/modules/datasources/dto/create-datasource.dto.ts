import { IsString, MinLength, IsOptional, IsObject, IsNumber, IsBoolean } from 'class-validator';

export class CreateDataSourceDto {
  @IsString()
  @MinLength(1)
  project_id: string;

  @IsString()
  @MinLength(1)
  source_type: string;

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
