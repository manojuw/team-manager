import { IsString, MinLength, IsOptional, IsObject, IsNumber, IsBoolean } from 'class-validator';

export class CreateDataSourceDto {
  @IsString()
  @MinLength(1)
  connectorId: string;

  @IsString()
  @MinLength(1)
  name: string;

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
