"""
Learning Routes - Train and apply learned cleaning rules.
"""

from typing import Any, Dict
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from services.dataset_analyzer import DatasetAnalyzer
from services.rule_miner import RuleMiner
from services.batch_processor import BatchProcessor, LearningEngine
from utils.auth import get_current_user, AuthUser

router = APIRouter(dependencies=[Depends(get_current_user)])


class AnalyzeFolderRequest(BaseModel):
    folder_path: str
    recursive: bool = True


class ProcessFolderRequest(BaseModel):
    folder_path: str
    output_folder: str = ""
    apply_cleaning: bool = True
    learn_rules: bool = True


@router.get("/rules")
async def get_rules(user: AuthUser = Depends(get_current_user)):
    """Get all learned cleaning rules."""
    try:
        processor = BatchProcessor()

        rules_by_domain = {}
        for domain, rules in processor.miner.domain_rules.items():
            rules_by_domain[domain] = [
                {
                    "rule_id": r.rule_id,
                    "name": r.name,
                    "action": r.action,
                    "confidence": r.confidence,
                    "auto_apply": r.auto_apply,
                    "times_applied": r.times_applied,
                }
                for r in rules
            ]

        return JSONResponse(
            {
                "success": True,
                "total_rules": len(processor.miner.rules),
                "auto_apply_rules": len(
                    [r for r in processor.miner.rules if r.auto_apply]
                ),
                "rules_by_domain": rules_by_domain,
                "stats": processor.get_stats(),
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze-folder")
async def analyze_folder(
    req: AnalyzeFolderRequest, user: AuthUser = Depends(get_current_user)
):
    """Analyze all datasets in a folder."""
    try:
        analyzer = DatasetAnalyzer()

        features_list = analyzer.analyze_folder(req.folder_path, req.recursive)

        results = []
        for features in features_list:
            results.append(
                {
                    "filename": features.filename,
                    "filepath": features.filepath,
                    "domain": features.detected_domain,
                    "domain_confidence": features.domain_confidence,
                    "rows": features.total_rows,
                    "columns": features.total_columns,
                    "currency_columns": features.currency_columns,
                    "error_placeholders": features.error_placeholders,
                    "quality_issues": features.quality_issues,
                }
            )

        return JSONResponse(
            {
                "success": True,
                "datasets_found": len(results),
                "domains_detected": {
                    d.domain: d.domain_confidence for d in features_list
                },
                "results": results,
                "stats": analyzer.get_stats(),
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mine-rules")
async def mine_rules(
    req: AnalyzeFolderRequest, user: AuthUser = Depends(get_current_user)
):
    """Analyze folder and mine new cleaning rules."""
    try:
        analyzer = DatasetAnalyzer()
        miner = RuleMiner()

        features_list = analyzer.analyze_folder(req.folder_path, req.recursive)

        new_rules = miner.mine_rules(features_list)

        return JSONResponse(
            {
                "success": True,
                "datasets_analyzed": len(features_list),
                "new_rules_generated": len(new_rules),
                "rules": [
                    {
                        "rule_id": r.rule_id,
                        "name": r.name,
                        "action": r.action,
                        "trigger_type": r.trigger_type,
                        "applicable_domains": r.applicable_domains,
                        "confidence": r.confidence,
                        "auto_apply": r.auto_apply,
                    }
                    for r in new_rules
                ],
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process-folder")
async def process_folder(
    req: ProcessFolderRequest, user: AuthUser = Depends(get_current_user)
):
    """Process all datasets in a folder with learned rules."""
    try:
        processor = BatchProcessor()

        session = processor.process_folder(
            folder_path=req.folder_path,
            output_folder=req.output_folder or None,
            apply_cleaning=req.apply_cleaning,
            learn_rules=req.learn_rules,
        )

        return JSONResponse(
            {
                "success": True,
                "session_id": session.session_id,
                "datasets_found": session.datasets_found,
                "datasets_processed": session.datasets_processed,
                "datasets_failed": session.datasets_failed,
                "total_cells_cleaned": session.total_cells_cleaned,
                "new_rules_generated": session.new_rules_generated,
                "domains_detected": session.domains_detected,
                "results": [
                    {
                        "filename": r.filename,
                        "domain": r.detected_domain,
                        "rows_before": r.rows_before,
                        "rows_after": r.rows_after,
                        "cells_cleaned": r.cells_cleaned,
                        "rules_applied": r.rules_applied,
                        "success": r.success,
                    }
                    for r in session.results
                ],
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/suggestions")
async def get_suggestions(folder_path: str, user: AuthUser = Depends(get_current_user)):
    """Get rule improvement suggestions based on folder analysis."""
    try:
        analyzer = DatasetAnalyzer()
        processor = BatchProcessor()

        features_list = analyzer.analyze_folder(folder_path)

        suggestions = processor.suggest_new_rules(features_list)

        return JSONResponse(
            {
                "success": True,
                "datasets_analyzed": len(features_list),
                "suggestions": suggestions,
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/export-rules")
async def export_rules(
    output_path: str = "data/learning/rules.json",
    user: AuthUser = Depends(get_current_user),
):
    """Export learned rules to file."""
    try:
        processor = BatchProcessor()
        processor.miner.export_rules(output_path)

        return JSONResponse(
            {
                "success": True,
                "message": f"Rules exported to {output_path}",
                "total_rules": len(processor.miner.rules),
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import-rules")
async def import_rules(
    input_path: str = "data/learning/rules.json",
    user: AuthUser = Depends(get_current_user),
):
    """Import rules from file."""
    try:
        processor = BatchProcessor()
        count = processor.miner.import_rules(input_path)

        return JSONResponse(
            {
                "success": True,
                "message": f"Imported {count} rules from {input_path}",
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
