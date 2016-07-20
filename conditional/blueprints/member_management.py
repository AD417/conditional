from flask import Blueprint
from flask import request
from flask import jsonify

from db.models import FreshmanAccount
from db.models import FreshmanEvalData
from db.models import FreshmanCommitteeAttendance
from db.models import MemberCommitteeAttendance
from db.models import FreshmanSeminarAttendance
from db.models import MemberSeminarAttendance
from db.models import FreshmanHouseMeetingAttendance
from db.models import MemberHouseMeetingAttendance
from db.models import HouseMeeting
from db.models import EvalSettings
from db.models import OnFloorStatusAssigned
from db.models import SpringEval

from util.ldap import ldap_is_eval_director
from util.ldap import ldap_is_financial_director
from util.ldap import ldap_set_roomnumber
from util.ldap import ldap_set_active
from util.ldap import ldap_set_housingpoints
from util.ldap import ldap_get_room_number
from util.ldap import ldap_get_housing_points
from util.ldap import ldap_is_active
from util.ldap import ldap_is_onfloor
from util.ldap import __ldap_add_member_to_group__ as ldap_add_member_to_group
from util.ldap import __ldap_remove_member_from_group__ as ldap_remove_member_from_group
from util.flask import render_template

import structlog
import uuid

logger = structlog.get_logger()

member_management_bp = Blueprint('member_management_bp', __name__)

@member_management_bp.route('/manage')
def display_member_management():
    log = logger.new(user_name=request.headers.get("x-webauth-user"),
            request_id=str(uuid.uuid4()))
    log.info('frontend', action='display member management')

    user_name = request.headers.get('x-webauth-user')

    if not ldap_is_eval_director(user_name) and not ldap_is_financial_director(user_name) and user_name != 'loothelion':
        return "must be eval director", 403

    settings = EvalSettings.query.first()
    return render_template(request, "member_management.html",
            username=user_name,
            housing_form_active=settings.housing_form_active,
            intro_form_active=settings.intro_form_active,
            site_lockdown=settings.site_lockdown)

@member_management_bp.route('/manage/settings', methods=['POST'])
def member_management_eval():
    log = logger.new(user_name=request.headers.get("x-webauth-user"),
            request_id=str(uuid.uuid4()))
    log.info('api', action='submit site-settings')

    user_name = request.headers.get('x-webauth-user')

    if not ldap_is_eval_director(user_name) and user_name != 'loothelion':
        return "must be eval director", 403

    post_data = request.get_json()

    if 'housing' in post_data:
        logger.info('backend', action="changed housing form activity to %s" % post_data['housing'])
        EvalSettings.query.update(
            {
                'housing_form_active': post_data['housing']
            })

    if 'intro' in post_data:
        logger.info('backend', action="changed intro form activity to %s" % post_data['intro'])
        EvalSettings.query.update(
            {
                'intro_form_active': post_data['intro']
            })

    if 'site_lockdown' in post_data:
        logger.info('backend', action="changed site lockdown to %s" % post_data['site_lockdown'])
        EvalSettings.query.update(
            {
                'site_lockdown': post_data['site_lockdown']
            })

    from db.database import db_session
    db_session.flush()
    db_session.commit()
    return jsonify({"success": True}), 200

@member_management_bp.route('/manage/adduser', methods=['POST'])
def member_management_adduser():
    log = logger.new(user_name=request.headers.get("x-webauth-user"),
            request_id=str(uuid.uuid4()))
    log.info('api', action='add fid user')

    from db.database import db_session

    user_name = request.headers.get('x-webauth-user')

    if not ldap_is_eval_director(user_name) and user_name != 'loothelion':
        return "must be eval director", 403

    post_data = request.get_json()

    name = post_data['name']
    onfloor_status = post_data['onfloor']

    logger.info('backend', action="add f_%s as onfloor: %s" % (name, onfloor_status))
    db_session.add(FreshmanAccount(name, onfloor_status))
    db_session.flush()
    db_session.commit()
    return jsonify({"success": True}), 200

@member_management_bp.route('/manage/edituser', methods=['POST'])
def member_management_edituser():
    log = logger.new(user_name=request.headers.get("x-webauth-user"),
            request_id=str(uuid.uuid4()))
    log.info('api', action='edit uid user')

    user_name = request.headers.get('x-webauth-user')

    if not ldap_is_eval_director(user_name) and not ldap_is_financial_director(user_name) and user_name != 'loothelion':
        return "must be eval director", 403

    post_data = request.get_json()

    uid = post_data['uid']
    active_member = post_data['active_member']

    if ldap_is_eval_director(user_name):
        logger.info('backend', action="edit %s room: %s onfloor: %s housepts %s" %
            (uid, post_data['room_number'], post_data['onfloor_status'], post_data['housing_points']))
        room_number = post_data['room_number']
        onfloor_status = post_data['onfloor_status']
        housing_points = post_data['housing_points']

        ldap_set_roomnumber(uid, room_number)
        if onfloor_status:
            ldap_add_member_to_group(uid, "onfloor")
        else:
            ldap_remove_member_from_group(uid, "onfloor")
        ldap_set_housingpoints(uid, housing_points)

    # Only update if there's a diff
    logger.info('backend', action="edit %s active: %s" % (uid, active_member))
    if ldap_is_active(uid) != active_member:
        ldap_set_active(uid, active_member)

        from db.database import db_session
        if active_member:
            db_session.add(SpringEval(uid))
        else:
            SpringEval.query.filter(
                SpringEval.uid == uid and
                SpringEval.active).update(
                {
                    'active': False
                })
        db_session.flush()
        db_session.commit()

    return jsonify({"success": True}), 200

@member_management_bp.route('/manage/getuserinfo', methods=['POST'])
def member_management_getuserinfo():
    log = logger.new(user_name=request.headers.get("x-webauth-user"),
            request_id=str(uuid.uuid4()))
    log.info('api', action='retreive user info')

    user_name = request.headers.get('x-webauth-user')

    if not ldap_is_eval_director(user_name) and not ldap_is_financial_director(user_name) and user_name != 'loothelion':
        return "must be eval or financial director", 403

    post_data = request.get_json()

    uid = post_data['uid']

    acct = FreshmanAccount.query.filter(
            FreshmanAccount.id == uid).first()

    # if fid
    if acct:
        return jsonify(
            {
                'user': 'fid'
            })

    if ldap_is_eval_director(user_name):

        # missed hm
        def get_hm_date(hm_id):
            return HouseMeeting.query.filter(
                HouseMeeting.id == hm_id).\
                first().date.strftime("%Y-%m-%d")

        missed_hm = [
            {
                'date': get_hm_date(hma.meeting_id),
                'id': hma.meeting_id,
                'excuse': hma.excuse,
                'status': hma.attendance_status
            } for hma in MemberHouseMeetingAttendance.query.filter(
                MemberHouseMeetingAttendance.uid == uid and
                (MemberHouseMeetingAttendance.attendance_status != attendance_enum.Attenaded))]

        hms_missed = []
        for hm in missed_hm:
            if hm['status'] != "Attended":
                hms_missed.append(hm)
        return jsonify(
            {
                'room_number': ldap_get_room_number(uid),
                'onfloor_status': ldap_is_onfloor(uid),
                'housing_points': ldap_get_housing_points(uid),
                'active_member': ldap_is_active(uid),
                'missed_hm': hms_missed,
                'user': 'eval'
            })
    else:
        return jsonify(
            {
                'active_member': ldap_is_active(uid),
                'user': 'financial'
            })

@member_management_bp.route('/manage/edit_hm_excuse', methods=['POST'])
def member_management_edit_hm_excuse():
    log = logger.new(user_name=request.headers.get("x-webauth-user"),
            request_id=str(uuid.uuid4()))
    log.info('api', action='edit house meeting excuse')

    user_name = request.headers.get('x-webauth-user')

    if not ldap_is_eval_director(user_name) and user_name != 'loothelion':
        return "must be eval director", 403

    post_data = request.get_json()

    hm_id = post_data['id']
    hm_status = post_data['status']
    hm_excuse = post_data['excuse']
    logger.info('backend', action="edit hm %s status: %s excuse: %s" %
        (hm_id, hm_status, hm_excuse))

    MemberHouseMeetingAttendance.query.filter(
        MemberHouseMeetingAttendance.id == hm_id).update(
        {
            'excuse': hm_excuse,
            'attendance_status': hm_status
        })

    from db.database import db_session
    db_session.flush()
    db_session.commit()
    return jsonify({"success": True}), 200


# TODO FIXME XXX Maybe change this to an endpoint where it can be called by our
# user creation script. There's no reason that the evals director should ever
# manually need to do this
@member_management_bp.route('/manage/upgrade_user', methods=['POST'])
def member_management_upgrade_user():
    log = logger.new(user_name=request.headers.get("x-webauth-user"),
            request_id=str(uuid.uuid4()))
    log.info('api', action='convert fid to uid entry')

    from db.database import db_session

    user_name = request.headers.get('x-webauth-user')

    if not ldap_is_eval_director(user_name) and user_name != 'loothelion':
        return "must be eval director", 403

    post_data = request.get_json()

    fid = post_data['fid']
    uid = post_data['uid']
    signatures_missed = post_data['sigsMissed']

    logger.info('backend', action="upgrade freshman-%s to %s sigsMissed: %s" %
        (fid, uid, signatures_missed))
    acct = FreshmanAccount.query.filter(
            FreshmanAccount.id == fid).first()

    new_acct = FreshmanEvalData(uid, signatures_missed)
    new_acct.eval_date = acct.eval_date

    db_session.add(new_acct)
    for fca in FreshmanCommitteeAttendance.query.filter(
        FreshmanCommitteeAttendance.fid == fid):
        db_session.add(MemberCommitteeAttendance(uid, fca.meeting_id))
        # XXX this might fail horribly #yoloswag
        db_session.delete(fca)

    for fts in FreshmanSeminarAttendance.query.filter(
        FreshmanSeminarAttendance.fid == fid):
        db_session.add(MemberSeminarAttendance(uid, fts.seminar_id))
        # XXX this might fail horribly #yoloswag
        db_session.delete(fts)

    for fhm in FreshmanHouseMeetingAttendance.query.filter(
        FreshmanHouseMeetingAttendance.fid == fid):
        db_session.add(MemberHouseMeetingAttendance(
            uid, fhm.meeting_id, fhm.excuse, fhm.attendance_status))
        # XXX this might fail horribly #yoloswag
        db_session.delete(fhm)

    if acct.onfloor_status:
        db_session.add(OnFloorStatusAssigned(uid, datetime.now()))

    # XXX this might fail horribly #yoloswag
    db_session.delete(acct)

    db_session.flush()
    db_session.commit()
    return jsonify({"success": True}), 200
