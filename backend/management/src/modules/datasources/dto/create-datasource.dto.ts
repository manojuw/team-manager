import { IsString, MinLength, IsOptional, IsObject, IsNumber, IsBoolean } from 'class-validator';

export class CreateDataSourceDto {
  @IsString()
  @MinLength(1)
  projectId: string;

  @IsString()
  @MinLength(1)
  sourceType: string;

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
